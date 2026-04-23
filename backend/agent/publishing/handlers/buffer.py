"""
Digital Force — Buffer API v1 Handler
======================================
Posts to any social platform via Buffer's scheduling API.

Buffer is the universal bridge: one account handles Facebook, Twitter, LinkedIn,
Instagram, TikTok, Pinterest — whatever you've connected in the Buffer dashboard.

Buffer API v1 endpoints used:
  GET  https://api.bufferapp.com/1/profiles.json           → list connected profiles
  POST https://api.bufferapp.com/1/updates/create.json     → create a post/update

Media support:
  - Images: accepted as a public URL via media[photo]=<url> or media[picture]=<url>
  - Videos: accepted as a public URL via media[video]=<url> (Buffer transcodes)
  - Text-only: fully supported with no media fields

Rate limits (enforced by Buffer internally per platform):
  - Twitter:   400 tweets/day per account
  - LinkedIn:  75 posts/day per account
  - Instagram: 25 posts/day per account (IG Graph API limit)
  - Facebook:  no strict API limit but spam filters apply
  These limits are enforced by Buffer automatically; our credential_pool adds
  a safety cap on top (DEFAULT_DAILY_LIMIT = 500 per Buffer credential).
"""

import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

BUFFER_API_BASE = "https://api.bufferapp.com/1"
BUFFER_TIMEOUT = 30   # seconds


# ── Profile Discovery ───────────────────────────────────────────────────────

async def get_profiles(access_token: str) -> list[dict]:
    """
    Fetch all social profiles connected to this Buffer account.

    Called automatically on /connect to populate connected_accounts.
    Can also be called manually via /refresh to pick up newly added profiles.

    Returns a list of profile dicts:
        [{
            "buffer_profile_id": "abc123",
            "platform": "twitter",
            "account_name": "@company",
            "account_id": "twitter_user_id",
            "profile_url": "https://twitter.com/company"
        }, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BUFFER_API_BASE}/profiles.json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            raw_profiles = resp.json()

        profiles = []
        for p in raw_profiles:
            service = p.get("service", "").lower()
            # Normalise Buffer service names to our platform naming
            platform_map = {
                "twitter": "twitter",
                "facebook": "facebook",
                "linkedin": "linkedin",
                "instagram": "instagram",
                "tiktok": "tiktok",
                "pinterest": "pinterest",
                "google": "youtube",
                "mastodon": "mastodon",
            }
            platform = platform_map.get(service, service)

            profiles.append({
                "buffer_profile_id": p.get("id", ""),
                "platform": platform,
                "account_name": p.get("formatted_username") or p.get("service_username", ""),
                "account_id": p.get("service_id", ""),
                "profile_url": p.get("service_username", ""),
            })

        logger.info(
            f"[Buffer] Fetched {len(profiles)} profile(s): "
            + ", ".join(f"{p['account_name']}({p['platform']})" for p in profiles)
        )
        return profiles

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            raise ValueError("Invalid or expired Buffer access token") from e
        raise


# ── Post Execution ──────────────────────────────────────────────────────────

async def post_to_buffer(
    access_token: str,
    profile_ids: list[str],
    content: str,
    media_urls: Optional[list[str]] = None,
    scheduled_at: Optional[str] = None,   # ISO 8601 UTC str, or None = post now
) -> dict:
    """
    Create a post/update via the Buffer API.

    Args:
        access_token:  Buffer API access token
        profile_ids:   List of Buffer profile IDs to post to (can be multiple → bulk post)
        content:       The text content of the post
        media_urls:    Optional list of public media URLs. Buffer accepts one image/video.
        scheduled_at:  ISO 8601 string for scheduled time. None = post to queue immediately.

    Returns:
        Success: {success: True, update_id, status, method: "buffer_api"}
        Failure: {success: False, error: str, token_expired: bool, rate_limited: bool}
    """
    if not profile_ids:
        return {"success": False, "error": "No Buffer profile IDs provided — cannot post"}
    if not access_token:
        return {"success": False, "error": "No Buffer access token provided"}

    # Build form-encoded data list (Buffer v1 uses form encoding, not JSON)
    data: list[tuple[str, str]] = []

    data.append(("text", content))

    # profile_ids[] as repeated params (Buffer's required multi-value format)
    for pid in profile_ids:
        data.append(("profile_ids[]", pid))

    # Scheduling
    if scheduled_at:
        data.append(("scheduled_at", scheduled_at))
    else:
        # Post to the top of the queue (Buffer sends at its optimal time or immediately)
        data.append(("now", "true"))

    # Media: Buffer takes one primary image/video
    if media_urls:
        first = media_urls[0]
        is_video = any(first.lower().endswith(ext) for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"))
        if is_video:
            data.append(("media[video]", first))
        else:
            data.append(("media[photo]", first))

        if len(media_urls) > 1:
            logger.info(
                f"[Buffer] Only 1 media item supported per Buffer post. "
                f"Ignoring {len(media_urls) - 1} additional URL(s)."
            )

    try:
        async with httpx.AsyncClient(timeout=BUFFER_TIMEOUT) as client:
            resp = await client.post(
                f"{BUFFER_API_BASE}/updates/create.json",
                headers={"Authorization": f"Bearer {access_token}"},
                data=data,
            )

        response_data = resp.json()
        logger.debug(f"[Buffer] API response ({resp.status_code}): {response_data}")

        # ── Success ──────────────────────────────────────────────────────────
        if resp.status_code in (200, 201) and response_data.get("success"):
            updates = response_data.get("updates", [])
            update = updates[0] if updates else {}
            return {
                "success": True,
                "update_id": update.get("id", ""),
                "status": update.get("status", "buffer"),        # "buffer" = queued
                "due_at": update.get("due_at", ""),
                "method": "buffer_api",
            }

        # ── Error handling ────────────────────────────────────────────────────
        error_msg = response_data.get("message", f"HTTP {resp.status_code}")
        error_code = response_data.get("code", 0)

        # Classify errors for the credential pool's fault-tolerance logic
        token_expired = resp.status_code == 403 or "access-token" in error_msg.lower()
        rate_limited = resp.status_code == 429 or "rate" in error_msg.lower()

        logger.error(
            f"[Buffer] Post failed (HTTP {resp.status_code}): {error_msg} "
            f"| token_expired={token_expired} | rate_limited={rate_limited}"
        )

        return {
            "success": False,
            "error": error_msg,
            "error_code": error_code,
            "token_expired": token_expired,
            "rate_limited": rate_limited,
        }

    except httpx.TimeoutException:
        return {"success": False, "error": f"Buffer API timeout after {BUFFER_TIMEOUT}s"}
    except Exception as e:
        logger.error(f"[Buffer] Unexpected error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ── Token Verification ──────────────────────────────────────────────────────

async def verify_token(access_token: str) -> dict:
    """
    Lightweight verification: fetch profiles and confirm the token is valid.
    Called by the /verify endpoint and automatically on /connect.

    Returns:
        {valid: True, profiles_count: N, platforms: [...]}
        {valid: False, error: "..."}
    """
    try:
        profiles = await get_profiles(access_token)
        platforms = list({p["platform"] for p in profiles})
        return {
            "valid": True,
            "profiles_count": len(profiles),
            "platforms": platforms,
            "profiles": profiles,
        }
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    except Exception as e:
        return {"valid": False, "error": f"Buffer API unreachable: {e}"}
