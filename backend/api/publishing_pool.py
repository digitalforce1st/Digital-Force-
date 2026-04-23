"""
Digital Force — Publishing Pool API
=====================================
REST endpoints for managing the Buffer credential fleet.

Workflow:
  1. POST /api/publishing-pool/connect  — paste token, auto-syncs profiles
  2. GET  /api/publishing-pool          — see all Buffer accounts + health
  3. POST /api/publishing-pool/{id}/refresh  — re-sync profiles from Buffer
  4. POST /api/publishing-pool/{id}/verify   — test the token is still valid
  5. DELETE /api/publishing-pool/{id}        — remove an account

Security:
  - credential_data (the access token) is NEVER returned in any GET response
  - Tokens are Fernet-encrypted at rest in the DB
  - All endpoints require JWT auth (get_current_user)
"""

import json
import uuid
import logging
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel

from database import get_db, ApiCredentialPool
from auth import get_current_user
from agent.publishing.credential_pool import (
    encrypt_credential,
    DEFAULT_DAILY_LIMIT,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/publishing-pool", tags=["publishing-pool"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConnectBufferRequest(BaseModel):
    """Body for POST /connect — the only endpoint the user interacts with."""
    label: str                   # "Brighton Buffer #1"
    access_token: str            # The Buffer API access token


class UpdateCredentialRequest(BaseModel):
    label: Optional[str] = None
    custom_daily_limit: Optional[int] = None
    status: Optional[str] = None    # "active" | "revoked"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_credential(cred: ApiCredentialPool) -> dict:
    """Serialize a credential for API response — NEVER includes credential_data."""
    today = date.today().isoformat()
    posts_today = cred.posts_today if cred.last_reset_date == today else 0
    daily_limit = cred.custom_daily_limit or DEFAULT_DAILY_LIMIT

    return {
        "id": cred.id,
        "label": cred.label,
        "api_type": cred.api_type,
        "status": cred.status,
        "platforms": json.loads(cred.platforms or "[]"),
        "connected_accounts": json.loads(cred.connected_accounts or "[]"),
        "posts_today": posts_today,
        "posts_this_hour": cred.posts_this_hour or 0,
        "daily_limit": daily_limit,
        "utilization_pct": round((posts_today / daily_limit) * 100, 1) if daily_limit else 0,
        "error_count": cred.error_count or 0,
        "success_count": cred.success_count or 0,
        "last_used_at": cred.last_used_at.isoformat() if cred.last_used_at else None,
        "last_error": cred.last_error,
        "last_verified_at": cred.last_verified_at.isoformat() if cred.last_verified_at else None,
        "created_at": cred.created_at.isoformat(),
        # Flag: tells the UI the token is set (but value is never sent)
        "has_token": bool(cred.credential_data),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_credentials(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all Buffer accounts in the publishing fleet for the current user."""
    user_id = user.get("sub")
    result = await db.execute(
        select(ApiCredentialPool)
        .where(ApiCredentialPool.user_id == user_id)
        .order_by(desc(ApiCredentialPool.created_at))
    )
    creds = result.scalars().all()
    return [_serialize_credential(c) for c in creds]


@router.get("/summary")
async def fleet_summary(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    High-level fleet health overview.
    Returns aggregate capacity, posts today, and per-platform breakdown.
    """
    user_id = user.get("sub")
    result = await db.execute(
        select(ApiCredentialPool).where(
            ApiCredentialPool.user_id == user_id,
            ApiCredentialPool.status == "active",
        )
    )
    creds = result.scalars().all()
    today = date.today().isoformat()

    total_capacity = sum(c.custom_daily_limit or DEFAULT_DAILY_LIMIT for c in creds)
    total_posts_today = sum(c.posts_today if c.last_reset_date == today else 0 for c in creds)

    # Per-platform profile count
    platform_counts: dict[str, int] = {}
    for cred in creds:
        for acc in json.loads(cred.connected_accounts or "[]"):
            p = acc.get("platform", "unknown")
            platform_counts[p] = platform_counts.get(p, 0) + 1

    return {
        "total_buffer_accounts": len(creds),
        "total_profiles": sum(platform_counts.values()),
        "platform_breakdown": platform_counts,
        "total_daily_capacity": total_capacity,
        "total_posts_today": total_posts_today,
        "utilization_pct": round((total_posts_today / total_capacity) * 100, 1) if total_capacity else 0,
        "accounts_at_error": sum(1 for c in creds if c.status == "error"),
    }


@router.post("/connect")
async def connect_buffer_account(
    body: ConnectBufferRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Connect a new Buffer account to the publishing fleet.

    Steps:
      1. Validates the token by calling the Buffer API
      2. Fetches and stores all connected social profiles
      3. Saves encrypted credentials to the DB
      4. Returns the full profile list immediately

    The user only needs to provide a label and their Buffer access token.
    Everything else (profiles, platforms) is auto-discovered.
    """
    from agent.publishing.handlers.buffer import verify_token, get_profiles

    user_id = user.get("sub")

    # Step 1: Validate the token and discover profiles
    verification = await verify_token(body.access_token)
    if not verification.get("valid"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Buffer token: {verification.get('error', 'Unknown error')}. "
                   "Check your token at https://buffer.com/developers/api/",
        )

    profiles = verification.get("profiles", [])
    platforms = list({p["platform"] for p in profiles})

    # Step 2: Encrypt the access token
    encrypted = encrypt_credential({"access_token": body.access_token})

    # Step 3: Save to DB
    cred = ApiCredentialPool(
        id=str(uuid.uuid4()),
        user_id=user_id,
        label=body.label,
        api_type="buffer",
        platforms=json.dumps(platforms),
        connected_accounts=json.dumps(profiles),
        credential_data=encrypted,
        status="active",
        posts_today=0,
        posts_this_hour=0,
        last_reset_date=date.today().isoformat(),
        last_reset_hour=datetime.utcnow().hour,
        error_count=0,
        success_count=0,
        last_verified_at=datetime.utcnow(),
    )
    db.add(cred)
    await db.commit()

    logger.info(
        f"[PublishingPool] Connected '{body.label}': "
        f"{len(profiles)} profile(s) across {platforms}"
    )

    return {
        "id": cred.id,
        "label": cred.label,
        "status": "active",
        "profiles_connected": len(profiles),
        "platforms": platforms,
        "connected_accounts": profiles,
        "message": (
            f"Successfully connected '{body.label}' with {len(profiles)} profile(s): "
            + ", ".join(f"{p['account_name']} ({p['platform']})" for p in profiles[:5])
            + ("..." if len(profiles) > 5 else "")
        ),
    }


@router.post("/{cred_id}/refresh")
async def refresh_profiles(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Re-sync connected profiles from the Buffer API.
    Use this after adding new social accounts to an existing Buffer account.
    """
    user_id = user.get("sub")
    cred = await db.get(ApiCredentialPool, cred_id)

    if not cred or cred.user_id != user_id:
        raise HTTPException(404, "Credential not found")

    from agent.publishing.credential_pool import decrypt_credential
    from agent.publishing.handlers.buffer import get_profiles

    cred_data = decrypt_credential(cred.credential_data)
    access_token = cred_data.get("access_token", "")

    try:
        profiles = await get_profiles(access_token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Buffer API error: {e}")

    platforms = list({p["platform"] for p in profiles})
    cred.connected_accounts = json.dumps(profiles)
    cred.platforms = json.dumps(platforms)
    cred.last_verified_at = datetime.utcnow()
    await db.commit()

    return {
        "refreshed": True,
        "profiles_count": len(profiles),
        "platforms": platforms,
        "connected_accounts": profiles,
    }


@router.post("/{cred_id}/verify")
async def verify_credential(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Test that the stored Buffer token is still valid by calling the Buffer API."""
    user_id = user.get("sub")
    cred = await db.get(ApiCredentialPool, cred_id)

    if not cred or cred.user_id != user_id:
        raise HTTPException(404, "Credential not found")

    from agent.publishing.credential_pool import decrypt_credential
    from agent.publishing.handlers.buffer import verify_token

    cred_data = decrypt_credential(cred.credential_data)
    result = await verify_token(cred_data.get("access_token", ""))

    cred.last_verified_at = datetime.utcnow()
    if result.get("valid"):
        if cred.status == "error" and cred.error_count < 5:
            cred.status = "active"   # Re-activate if manually verified
        cred.last_error = None
    else:
        cred.last_error = result.get("error", "Verification failed")[:500]
        if "invalid" in str(result.get("error", "")).lower():
            cred.status = "revoked"

    await db.commit()
    return {"id": cred_id, "valid": result.get("valid"), "details": result}


@router.put("/{cred_id}")
async def update_credential(
    cred_id: str,
    body: UpdateCredentialRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update the label, daily limit, or activation status of a credential."""
    user_id = user.get("sub")
    cred = await db.get(ApiCredentialPool, cred_id)

    if not cred or cred.user_id != user_id:
        raise HTTPException(404, "Credential not found")

    if body.label is not None:
        cred.label = body.label
    if body.custom_daily_limit is not None:
        cred.custom_daily_limit = body.custom_daily_limit
    if body.status is not None:
        if body.status not in ("active", "revoked"):
            raise HTTPException(400, "status must be 'active' or 'revoked'")
        cred.status = body.status
        if body.status == "active":
            # Clear error state when manually reactivating
            cred.error_count = 0
            cred.last_error = None

    await db.commit()
    return {"id": cred.id, "label": cred.label, "status": cred.status, "updated": True}


@router.post("/{cred_id}/reset-counters")
async def reset_counters(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Manually reset daily and hourly post counters (e.g. after testing)."""
    user_id = user.get("sub")
    cred = await db.get(ApiCredentialPool, cred_id)

    if not cred or cred.user_id != user_id:
        raise HTTPException(404, "Credential not found")

    cred.posts_today = 0
    cred.posts_this_hour = 0
    cred.last_reset_date = date.today().isoformat()
    cred.last_reset_hour = datetime.utcnow().hour
    if cred.status == "exhausted":
        cred.status = "active"

    await db.commit()
    return {"reset": True, "posts_today": 0, "posts_this_hour": 0}


@router.delete("/{cred_id}")
async def delete_credential(
    cred_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Remove a Buffer account from the publishing fleet."""
    user_id = user.get("sub")
    cred = await db.get(ApiCredentialPool, cred_id)

    if not cred or cred.user_id != user_id:
        raise HTTPException(404, "Credential not found")

    label = cred.label
    await db.delete(cred)
    await db.commit()

    logger.info(f"[PublishingPool] Removed credential '{label}' ({cred_id})")
    return {"deleted": True, "id": cred_id, "label": label}
