"""
Digital Force — API Credential Pool Manager
============================================
Manages the dynamic fleet of Buffer API credentials for publishing.

Architecture:
  - Each Buffer account is ONE row in ApiCredentialPool
  - One Buffer account can serve multiple platforms (FB, Twitter, LinkedIn, IG, etc.)
  - Multiple Buffer accounts = horizontal scale (no rate limit ceiling)
  - credential_data is Fernet-encrypted at rest; decrypted only at post time
  - Credentials are ranked by: account-name-match first, fewest-posts-today second
  - Auto-disables credentials after 5 consecutive failures

Scale target: 200–500 posts/day across 30+ accounts and 6+ platforms.
"""

import json
import logging
import hashlib
import base64
from datetime import datetime, date
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Default daily post limit per Buffer credential (our safety cap)
# Buffer's actual limits depend on their plan; this prevents runaway execution
DEFAULT_DAILY_LIMIT = 500


# ── Encryption / Decryption ─────────────────────────────────────────────────

def _get_fernet():
    """
    Derive a valid 32-byte Fernet key from whatever string is in config.encryption_key.
    SHA-256 always produces exactly 32 bytes, regardless of input length.
    This means ANY encryption_key value — including the default placeholder — works,
    though you must use the SAME key to decrypt what you encrypted.
    """
    from cryptography.fernet import Fernet
    raw = settings.encryption_key.encode()
    derived = hashlib.sha256(raw).digest()        # Always 32 bytes
    fernet_key = base64.urlsafe_b64encode(derived)  # Fernet requires URL-safe b64
    return Fernet(fernet_key)


def encrypt_credential(data: dict) -> str:
    """Encrypt a credential dict and return a base64 Fernet ciphertext string."""
    f = _get_fernet()
    return f.encrypt(json.dumps(data).encode()).decode()


def decrypt_credential(ciphertext: str) -> dict:
    """Decrypt a Fernet ciphertext string back to a credential dict."""
    try:
        f = _get_fernet()
        return json.loads(f.decrypt(ciphertext.encode()).decode())
    except Exception as e:
        logger.error(f"[CredentialPool] Decryption failed: {e}")
        return {}


# ── Daily limit helpers ─────────────────────────────────────────────────────

def _is_at_daily_limit(credential, today: str) -> bool:
    """Return True if this credential has hit its daily post limit."""
    if credential.last_reset_date != today:
        return False   # Counter hasn't been reset yet → treat as 0
    limit = credential.custom_daily_limit or DEFAULT_DAILY_LIMIT
    return credential.posts_today >= limit


def _get_posts_today(credential) -> int:
    """Return effective posts_today (0 if it's a new day and hasn't been reset yet)."""
    today = date.today().isoformat()
    if credential.last_reset_date != today:
        return 0
    return credential.posts_today or 0


# ── Pool Query ──────────────────────────────────────────────────────────────

async def get_credentials_for(
    platform: str,
    user_id: str,
    account_name: Optional[str] = None,
) -> list[dict]:
    """
    Query the pool for all usable Buffer credentials for a given platform.

    Filters:
      1. Status must be "active"
      2. Platform must be in the credential's platforms list
      3. Must not have hit daily limit

    Ranking (best first):
      1. Credentials with a connected_account matching account_name (exact/partial)
      2. Among equals: fewer posts_today wins (load balance)

    Returns a list of dicts, each containing:
      {credential_id, label, cred_data (decrypted), buffer_profile_id, posts_today}
    """
    from database import async_session, ApiCredentialPool
    from sqlalchemy import select

    today = date.today().isoformat()
    platform_lower = platform.lower()

    async with async_session() as db:
        result = await db.execute(
            select(ApiCredentialPool).where(
                ApiCredentialPool.user_id == user_id,
                ApiCredentialPool.status == "active",
            )
        )
        all_creds = result.scalars().all()

    usable = []
    for cred in all_creds:
        # Platform match
        supported = [p.lower() for p in json.loads(cred.platforms or "[]")]
        if platform_lower not in supported:
            continue

        # Daily limit check
        if _is_at_daily_limit(cred, today):
            logger.debug(f"[CredentialPool] '{cred.label}' at daily limit — skipping")
            continue

        # Try to find the matching Buffer profile for this platform + account
        connected = json.loads(cred.connected_accounts or "[]")
        buffer_profile_id = None
        account_matched = False

        for acc in connected:
            if acc.get("platform", "").lower() != platform_lower:
                continue
            if account_name:
                # Partial match: account_name appears in account_name field (case-insensitive)
                if account_name.lower() in acc.get("account_name", "").lower():
                    buffer_profile_id = acc.get("buffer_profile_id")
                    account_matched = True
                    break
            else:
                # No specific account requested — take first profile for this platform
                buffer_profile_id = acc.get("buffer_profile_id")
                account_matched = True
                break

        # We have a profile (or no account was specified and we found any)
        if not buffer_profile_id:
            # Skip if we need an account match but didn't find one
            if account_name:
                continue
            # Fall through — we'll post to first connected profile of this platform
            for acc in connected:
                if acc.get("platform", "").lower() == platform_lower:
                    buffer_profile_id = acc.get("buffer_profile_id")
                    break

        if not buffer_profile_id:
            continue   # No profiles for this platform at all

        # Decrypt credentials
        try:
            cred_data = decrypt_credential(cred.credential_data)
        except Exception:
            logger.warning(f"[CredentialPool] Could not decrypt '{cred.label}' — skipping")
            continue

        usable.append({
            "credential_id": cred.id,
            "label": cred.label,
            "cred_data": cred_data,
            "buffer_profile_id": buffer_profile_id,
            "account_matched": account_matched,
            "posts_today": _get_posts_today(cred),
        })

    # Rank: account-matched first, then fewest posts today
    usable.sort(key=lambda c: (-int(c["account_matched"]), c["posts_today"]))
    logger.info(
        f"[CredentialPool] Found {len(usable)} usable credential(s) for "
        f"platform='{platform}' account='{account_name or 'any'}'"
    )
    return usable


# ── Primary Execution Function ──────────────────────────────────────────────

async def post_with_best_credential(
    platform: str,
    user_id: str,
    content: str,
    media_urls: list[str],
    account_name: Optional[str] = None,
    scheduled_at: Optional[str] = None,
) -> dict:
    """
    The ONE function the scheduler calls for every post.

    Tries each ranked credential in order until one succeeds.
    Returns first success, or descriptive error if all fail.

    Return format:
      Success: {success: True, update_id, method: "buffer_api", credential_label, ...}
      No creds: {success: False, no_credentials: True, error: "..."}
      All failed: {success: False, all_failed: True, tried: N, error: "..."}
    """
    from agent.publishing.handlers.buffer import post_to_buffer

    creds = await get_credentials_for(platform, user_id, account_name)

    if not creds:
        msg = (
            f"No Buffer credentials configured for '{platform}'. "
            f"Add a Buffer account in Settings → Publishing Accounts."
        )
        logger.warning(f"[CredentialPool] {msg}")
        return {"success": False, "no_credentials": True, "error": msg}

    last_error = "Unknown error"
    tried = 0

    for cred in creds:
        tried += 1
        access_token = cred["cred_data"].get("access_token", "")
        profile_id = cred["buffer_profile_id"]

        if not access_token:
            logger.warning(f"[CredentialPool] '{cred['label']}' has no access_token — skipping")
            continue
        if not profile_id:
            logger.warning(f"[CredentialPool] '{cred['label']}' has no profile_id for {platform} — skipping")
            continue

        logger.info(
            f"[CredentialPool] Attempting '{cred['label']}' → "
            f"Buffer profile {profile_id} for platform {platform} "
            f"(posts today: {cred['posts_today']})"
        )

        result = await post_to_buffer(
            access_token=access_token,
            profile_ids=[profile_id],
            content=content,
            media_urls=media_urls or None,
            scheduled_at=scheduled_at,
        )

        if result.get("success"):
            await record_post(cred["credential_id"], success=True)
            return {
                **result,
                "credential_id": cred["credential_id"],
                "credential_label": cred["label"],
                "buffer_profile_id": profile_id,
            }

        # Credential failed
        last_error = result.get("error", "Unknown")
        logger.warning(f"[CredentialPool] '{cred['label']}' failed: {last_error}")
        await record_post(cred["credential_id"], success=False)

        if result.get("token_expired"):
            await mark_error(cred["credential_id"], last_error, permanent=True)

    return {
        "success": False,
        "all_failed": True,
        "tried": tried,
        "error": f"All {tried} Buffer credential(s) failed for '{platform}'. Last error: {last_error}",
    }


# ── Accounting ──────────────────────────────────────────────────────────────

async def record_post(credential_id: str, success: bool = True) -> None:
    """Increment post counters and update health stats for a credential."""
    from database import async_session, ApiCredentialPool

    today = date.today().isoformat()
    now = datetime.utcnow()
    hour = now.hour

    async with async_session() as db:
        cred = await db.get(ApiCredentialPool, credential_id)
        if not cred:
            return

        # Reset daily counter if it's a new day
        if cred.last_reset_date != today:
            cred.posts_today = 0
            cred.last_reset_date = today

        # Reset hourly counter if it's a new hour
        if cred.last_reset_hour != hour:
            cred.posts_this_hour = 0
            cred.last_reset_hour = hour

        cred.posts_today = (cred.posts_today or 0) + 1
        cred.posts_this_hour = (cred.posts_this_hour or 0) + 1
        cred.last_used_at = now

        if success:
            cred.success_count = (cred.success_count or 0) + 1
            cred.error_count = 0           # Reset consecutive failure streak
        else:
            cred.error_count = (cred.error_count or 0) + 1
            if cred.error_count >= 5:
                cred.status = "error"
                logger.warning(
                    f"[CredentialPool] '{cred.label}' auto-disabled after "
                    f"5 consecutive failures. Reactivate in Settings."
                )

        await db.commit()


async def mark_error(credential_id: str, error: str, permanent: bool = False) -> None:
    """Flag a credential error. If permanent=True, revoke it immediately."""
    from database import async_session, ApiCredentialPool

    async with async_session() as db:
        cred = await db.get(ApiCredentialPool, credential_id)
        if not cred:
            return
        cred.last_error = str(error)[:500]
        cred.error_count = (cred.error_count or 0) + 1
        if permanent:
            cred.status = "revoked"
            logger.error(
                f"[CredentialPool] '{cred.label}' permanently revoked "
                f"(token expired or invalid): {error[:100]}"
            )
        elif cred.error_count >= 5:
            cred.status = "error"
        await db.commit()
