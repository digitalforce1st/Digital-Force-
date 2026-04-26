from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import uuid

from database import get_db, PlatformConnection
from auth import get_current_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

class AccountCreate(BaseModel):
    platform: str
    display_name: str
    account_label: str
    auth_data: Optional[str] = None
    account_name: Optional[str] = None

class AccountUpdate(BaseModel):
    display_name: Optional[str] = None
    account_label: Optional[str] = None
    auth_data: Optional[str] = None
    is_enabled: Optional[bool] = None

@router.get("", response_model=List[dict])
async def list_accounts(db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    import logging
    _logger = logging.getLogger(__name__)
    user_id = current_user.get("sub")
    # Return ALL accounts for any authenticated operator (single-agency platform)
    stmt = select(PlatformConnection)
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    _logger.info(f"[Accounts] Listing {len(accounts)} accounts (requested by user {user_id})")
    out = []
    for a in accounts:
        out.append({
            "id": a.id,
            "platform": a.platform,
            "display_name": a.display_name,
            "account_label": a.account_label,
            "account_name": a.account_name,
            "auth_data": a.auth_data,
            "is_enabled": a.is_enabled,
            "connection_status": a.connection_status
        })
    return out

@router.post("")
async def create_account(account: AccountCreate, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    new_account = PlatformConnection(
        id=str(uuid.uuid4()),
        user_id=current_user.get("sub"),
        platform=account.platform,
        display_name=account.display_name,
        account_label=account.account_label,
        auth_data=account.auth_data,
        account_name=account.account_name,
        is_enabled=True,
        connection_status="pending",  # Must be verified via Ghost Browser auth
    )
    db.add(new_account)
    await db.commit()
    return {"status": "success", "id": new_account.id}

@router.put("/{account_id}")
async def update_account(account_id: str, updates: AccountUpdate, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    stmt = select(PlatformConnection).where(PlatformConnection.id == account_id)
    result = await db.execute(stmt)
    acc = result.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    exclude = updates.model_dump(exclude_unset=True)
    for k, v in exclude.items():
        setattr(acc, k, v)
        
    await db.commit()
    return {"status": "success"}

@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    stmt = select(PlatformConnection).where(PlatformConnection.id == account_id)
    result = await db.execute(stmt)
    acc = result.scalar_one_or_none()
    if acc:
        await db.delete(acc)
        await db.commit()
    return {"status": "success"}

@router.post("/{account_id}/provision")
async def provision_account(account_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Fires a deep ReAct browser agent to physically connect a social account.

    The agent:
    1. Navigates to the platform login page
    2. Uses Ghost Browser vision to locate and fill the login form
    3. Handles 2FA, CAPTCHAs, and QR codes by communicating through the Agentic Hub
    4. On success, updates connection_status = 'connected' and stores session cookies
    5. On failure, updates connection_status = 'needs_reauth' and reports why

    All progress is pushed live to the user's chat via chat_push.
    """
    from database import Goal
    from agent.chat_push import chat_push
    import json
    import asyncio

    stmt = select(PlatformConnection).where(PlatformConnection.id == account_id)
    result = await db.execute(stmt)
    acc = result.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    user_id = current_user.get("sub", "")

    # Mark as connecting immediately so the UI shows feedback
    acc.connection_status = "connecting"
    await db.commit()

    # Build a rich goal description with all credential context for the agent
    goal_description = f"""SYSTEM_AUTH_PROVISION: Connect the social media account described below using the Ghost Browser agent.

Platform: {acc.platform}
Account Display Name: {acc.display_name}
Account Label: {acc.account_label}
Account ID (Truth Bucket): {acc.id}
Credentials / Auth Instructions:
{acc.auth_data or 'No credentials provided. Check the platform for OAuth flow.'}

AGENT INSTRUCTIONS:
1. Navigate to the {acc.platform} login page
2. Use ghost_see to analyze the page and locate the login form
3. Use ghost_type to enter credentials naturally (human-speed keystrokes)
4. Handle any 2FA, SMS code, or CAPTCHA by communicating through chat_push asking the operator
5. If a QR code is required (WhatsApp, WeChat), take a screenshot and push it to the operator via chat
6. On successful login, verify the session by checking the post-login page
7. Update the account connection_status to 'connected' in the database
8. If login fails after 3 attempts, update connection_status to 'needs_reauth' and explain why

Always report progress steps through the Agentic Hub so the operator can see what is happening.
Never store raw passwords in logs."""

    goal_id = str(uuid.uuid4())
    new_goal = Goal(
        id=goal_id,
        created_by=user_id,
        title=f"Connect {acc.platform.capitalize()} — {acc.account_label}",
        description=goal_description,
        platforms=json.dumps([acc.platform]),
        status="executing",
    )
    db.add(new_goal)
    await db.commit()

    # Push immediate feedback to the Agentic Hub
    await chat_push(
        user_id=user_id,
        content=f"Browser agent dispatched to connect {acc.platform.capitalize()} account \"{acc.display_name}\". "
                f"I will report every step here. If I need anything from you (2FA code, QR scan, CAPTCHA), I will ask here.",
        agent_name="skillforge",
        goal_id=goal_id,
    )

    # Fire the Orchestrator ReAct Loop in the background (GC-safe)
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from langclaw_agents.orchestrator_app import run_orchestration
        from langclaw_agents.monologue_worker import _safe_create_task
        _safe_create_task(run_orchestration(goal_id, trigger_source="settings_provision"))
    except Exception as e:
        _logger.error(f"Failed to dispatch auth provision: {e}")

    return {"status": "provisioning", "goal_id": goal_id, "account_id": account_id}

@router.post("/{account_id}/ghost-auth/start")
async def ghost_auth_start(account_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Spins up a visible (headless=False) Playwright browser context specifically bound to this account's session.
    Navigates to the platform so the user can manually log in and complete 2FA.
    """
    from agent.browser.ghost import ghost

    stmt = select(PlatformConnection).where(PlatformConnection.id == account_id)
    result = await db.execute(stmt)
    acc = result.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    # Always ensure Ghost is running — safe to call multiple times
    if not ghost.is_running:
        await ghost.start()

    if not ghost.is_running:
        raise HTTPException(status_code=503, detail="Ghost Browser failed to start — ensure Playwright is installed (pip install playwright && playwright install chromium)")

    PLATFORM_LOGIN_URLS = {
        "facebook":  "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/accounts/login/",
        "twitter":   "https://twitter.com/login",
        "tiktok":    "https://www.tiktok.com/login",
        "linkedin":  "https://www.linkedin.com/login",
        "youtube":   "https://accounts.google.com/signin",
        "pinterest": "https://www.pinterest.com/login/",
    }
    url = PLATFORM_LOGIN_URLS.get(acc.platform.lower(), f"https://www.{acc.platform.lower()}.com/login")

    try:
        page = await ghost.get_page(account_id=acc.id, headless=False)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Mark the account as having an open browser session
        acc.connection_status = "browser_open"
        await db.commit()

        return {"status": "browser_opened", "url": url}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            f"[GhostAuth] Browser launch failed for account {account_id} "
            f"({acc.platform}): {type(e).__name__}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Browser launch failed ({type(e).__name__}): {str(e)}. "
                   f"Ensure Playwright is installed: pip install playwright && playwright install chromium"
        )


@router.post("/{account_id}/ghost-auth/verify")
async def ghost_auth_verify(account_id: str, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Called when the user clicks 'I've Logged In'.
    Marks the account as connected in the DB first (so the UI updates even if the
    browser close step fails), then safely releases the Playwright context.
    """
    import logging
    _logger = logging.getLogger(__name__)

    stmt = select(PlatformConnection).where(PlatformConnection.id == account_id)
    result = await db.execute(stmt)
    acc = result.scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    # ── Step 1: Commit the status update FIRST so it can never be rolled back ──
    # We flush immediately so the DB record is durable before we touch the browser.
    acc.connection_status = "connected"
    acc.is_enabled = True
    await db.commit()
    _logger.info(f"[GhostAuth] Account {account_id} ({acc.display_name}) marked as connected")

    # ── Step 2: Close the browser context (non-fatal if it fails) ─────────────
    # Context may not be in memory if the server restarted between the
    # browser open and verify steps — that's okay, the session cookies were
    # already written to disk by Playwright's persistent context.
    try:
        from agent.browser.ghost import ghost
        await ghost.close_context(acc.id)
        _logger.info(f"[GhostAuth] Browser context released for {account_id}")
    except Exception as e:
        _logger.warning(f"[GhostAuth] Could not close browser context (non-fatal): {e}")

    return {"status": "success", "connection_status": "connected"}
