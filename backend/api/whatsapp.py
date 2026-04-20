"""
Digital Force — WhatsApp Web Authentication API
Provides endpoints to check and initiate the WhatsApp Web QR scan flow
using the persistent Ghost Browser session.
"""

import asyncio
import base64
import logging
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

QR_PATH = Path(__file__).parent.parent / "media" / "qr_codes" / "whatsapp_qr.png"
TIMEOUT_FLAG = Path(__file__).parent.parent / "media" / "qr_codes" / "whatsapp_timeout.flag"


@router.get("/status")
async def whatsapp_status(user: dict = Depends(get_current_user)):
    """
    Check whether WhatsApp Web is authenticated in the Ghost Browser session.
    Returns: authenticated (bool), qr_available (bool), qr_image_b64 (str|None)
    """
    from agent.browser.ghost import ghost

    # Check if a whatsapp_automation context already has a valid session
    session_dir = Path(__file__).parent.parent / "ghost_session_data" / "whatsapp_automation"
    session_exists = session_dir.exists() and any(session_dir.iterdir())

    qr_available = QR_PATH.exists()
    qr_b64 = None
    if qr_available:
        try:
            qr_b64 = base64.b64encode(QR_PATH.read_bytes()).decode()
        except Exception:
            qr_b64 = None

    response_data = {
        "authenticated": session_exists and not qr_available,
        "session_dir_exists": session_exists,
        "qr_available": qr_available,
        "qr_image_b64": qr_b64,
        "timeout_detected": TIMEOUT_FLAG.exists(),
    }
    
    return JSONResponse(
        content=response_data,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/request-qr")
async def request_whatsapp_qr(user: dict = Depends(get_current_user)):
    """
    Triggers the Ghost Browser to open WhatsApp Web and capture the QR code.
    The QR image is returned as base64. Scan it with your phone to authenticate.
    This endpoint runs the browser flow in a background task and returns immediately.
    """
    from agent.browser.ghost import ghost

    async def _do_qr_capture():
        try:
            # Delete any stale QR image first
            if QR_PATH.exists():
                QR_PATH.unlink()
            if TIMEOUT_FLAG.exists():
                TIMEOUT_FLAG.unlink()

            page = await ghost.get_page(account_id="whatsapp_automation")
            logger.info("[WhatsApp QR] Navigating to WhatsApp Web for QR capture...")
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")

            # Wait for QR canvas or the chat UI (if already authed)
            try:
                # Give the page a bit more time to render JS
                await page.wait_for_timeout(5000)

                element = await page.wait_for_selector(
                    'canvas, div[title="Type a message"], div[data-testid="chat-list"]',
                    timeout=30000,
                )
                tag = await element.evaluate("el => el.tagName.toLowerCase()")

                if tag == "canvas":
                    QR_PATH.parent.mkdir(parents=True, exist_ok=True)
                    # We might need to grab the closest parent to get a clean crop, 
                    # but canvas usually draws exactly the QR bounds.
                    await element.screenshot(path=str(QR_PATH))
                    logger.info(f"[WhatsApp QR] QR code captured → {QR_PATH}")
                else:
                    # Already authenticated — clear any leftover QR file
                    if QR_PATH.exists():
                        QR_PATH.unlink()
                    logger.info("[WhatsApp QR] Session is already authenticated!")
            except Exception as e:
                logger.warning(f"[WhatsApp QR] Timeout waiting for page: {e}")
                TIMEOUT_FLAG.parent.mkdir(parents=True, exist_ok=True)
                TIMEOUT_FLAG.touch()
                # Capture the state of the page so we can debug!
                debug_path = QR_PATH.parent / "whatsapp_debug_screenshot.png"
                await page.screenshot(path=str(debug_path))
                logger.info(f"[WhatsApp QR] Debug page screenshot grabbed → {debug_path}")

            await page.close()
        except Exception as e:
            logger.error(f"[WhatsApp QR] Failed to capture QR: {e}", exc_info=True)

    # Fire in background so we can return a 202 immediately
    asyncio.create_task(_do_qr_capture())

    return JSONResponse(
        status_code=202,
        content={
            "status": "capturing",
            "message": "QR code capture started. Poll GET /api/whatsapp/status in ~5 seconds for the result.",
        },
    )


@router.post("/clear-session")
async def clear_whatsapp_session(user: dict = Depends(get_current_user)):
    """
    Wipes the WhatsApp Web browser session so you can re-authenticate
    with a fresh QR scan. Useful if the session has expired.
    """
    import shutil
    from agent.browser.ghost import ghost

    session_dir = Path(__file__).parent.parent / "ghost_session_data" / "whatsapp_automation"

    # Close the live context if it exists
    if "whatsapp_automation" in ghost._contexts:
        try:
            await ghost._contexts["whatsapp_automation"].close()
            del ghost._contexts["whatsapp_automation"]
        except Exception as e:
            logger.warning(f"[WhatsApp] Could not close live context: {e}")

    # Wipe session data on disk
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.info("[WhatsApp] Session directory wiped.")

    # Clear stale QR image
    if QR_PATH.exists():
        QR_PATH.unlink()
    if TIMEOUT_FLAG.exists():
        TIMEOUT_FLAG.unlink()

    return {"status": "cleared", "message": "WhatsApp session cleared. Request a fresh QR code to re-authenticate."}
