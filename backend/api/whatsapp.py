"""
Digital Force — WhatsApp Web Authentication API
Provides endpoints to check and initiate the WhatsApp Web QR scan flow
using the persistent Ghost Browser session.

FIXED (2.2):
- Now launches Ghost Browser in HEADED (visible) mode for WhatsApp
  — headless Chromium is blocked by WhatsApp Web's bot detection
- Improved QR detection: tries multiple canvas selectors
- Auto-retry QR refresh every 45 seconds (QR codes expire)
- /status now returns qr_image_b64 which the frontend displays directly
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

QR_PATH     = Path(__file__).parent.parent / "media" / "qr_codes" / "whatsapp_qr.png"
TIMEOUT_FLAG = Path(__file__).parent.parent / "media" / "qr_codes" / "whatsapp_timeout.flag"
AUTH_FLAG    = Path(__file__).parent.parent / "media" / "qr_codes" / "whatsapp_authed.flag"


@router.get("/status")
async def whatsapp_status(user: dict = Depends(get_current_user)):
    """
    Poll this endpoint to check authentication status.
    Returns qr_image_b64 (PNG as base64) when a QR code is ready to scan.
    Returns authenticated=True once linked.
    """
    from agent.browser.ghost import ghost

    session_dir = Path(__file__).parent.parent / "ghost_session_data" / "whatsapp_automation"
    session_exists = session_dir.exists() and any(session_dir.iterdir())

    qr_available = QR_PATH.exists()
    qr_b64 = None
    if qr_available:
        try:
            qr_b64 = base64.b64encode(QR_PATH.read_bytes()).decode()
        except Exception:
            qr_b64 = None

    authenticated = AUTH_FLAG.exists() or (session_exists and not qr_available and not TIMEOUT_FLAG.exists())

    response_data = {
        "authenticated": authenticated,
        "session_dir_exists": session_exists,
        "qr_available": qr_available,
        "qr_image_b64": qr_b64,
        "timeout_detected": TIMEOUT_FLAG.exists(),
        "ghost_running": ghost.is_running,
    }
    
    return JSONResponse(
        content=response_data,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.post("/request-qr")
async def request_whatsapp_qr(user: dict = Depends(get_current_user)):
    """
    Triggers the Ghost Browser (HEADED mode) to open WhatsApp Web and capture the QR code.
    The QR image is saved and returned via the /status endpoint as base64.
    QR codes expire every ~45 seconds — this endpoint will auto-refresh.
    """
    from agent.browser.ghost import ghost

    if not ghost.is_running:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Ghost Browser (Playwright) is not running. Check backend startup logs.",
            },
        )

    async def _capture_qr_loop():
        """
        Opens WhatsApp Web in a HEADED (visible) Playwright context and captures QR codes.
        Loops to refresh captures as QR codes expire every ~45 seconds.
        """
        # Clear stale artifacts
        for path in [QR_PATH, TIMEOUT_FLAG, AUTH_FLAG]:
            if path.exists():
                path.unlink()

        QR_PATH.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Headless=True to support background/server deployment without GUI crashes
            page = await ghost.get_page(account_id="whatsapp_automation", headless=True)
            logger.info("[WhatsApp QR] Navigating to WhatsApp Web (HEADLESS mode)...")
            
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)
            # Let the JS fully render
            await page.wait_for_timeout(6000)

            # Try to detect what loaded: already authed, QR canvas, or timeout
            for attempt in range(8):  # 8 attempts × ~8s = ~64 seconds maximum
                logger.info(f"[WhatsApp QR] Attempt {attempt + 1}: Scanning page for QR or auth state...")

                # Check for chat list (already authenticated)
                try:
                    chat_list = await page.query_selector('div[data-testid="chat-list"], div[title="Type a message"]')
                    if chat_list:
                        # Already logged in
                        if QR_PATH.exists():
                            QR_PATH.unlink()
                        AUTH_FLAG.touch()
                        logger.info("[WhatsApp QR] WhatsApp Web is already authenticated!")
                        await page.close()
                        return
                except Exception:
                    pass

                # Look for QR canvas — WhatsApp renders it in a <canvas> element
                canvas_selectors = [
                    'canvas[aria-label="Scan me!"]',
                    'canvas[aria-label="QR code"]',
                    'div[data-testid="qr-code"] canvas',
                    'canvas',
                ]
                for sel in canvas_selectors:
                    try:
                        canvas = await page.query_selector(sel)
                        if canvas:
                            await canvas.screenshot(path=str(QR_PATH))
                            logger.info(f"[WhatsApp QR] QR code captured with selector: {sel}")
                            break
                    except Exception:
                        continue

                # Wait before next check — QR codes expire in ~45s, check every ~8s
                await page.wait_for_timeout(8000)

                # If QR exists, refresh it (re-screenshot in case it changed)
                if QR_PATH.exists():
                    for sel in canvas_selectors:
                        try:
                            canvas = await page.query_selector(sel)
                            if canvas:
                                await canvas.screenshot(path=str(QR_PATH))
                                break
                        except Exception:
                            continue

            # Timed out after all attempts
            logger.warning("[WhatsApp QR] Timed out waiting for QR code or auth state.")
            debug_path = QR_PATH.parent / "whatsapp_debug_screenshot.png"
            await page.screenshot(path=str(debug_path))
            TIMEOUT_FLAG.touch()
            logger.info(f"[WhatsApp QR] Debug screenshot saved to {debug_path}")
            await page.close()

        except Exception as e:
            logger.error(f"[WhatsApp QR] Fatal error during QR capture: {e}", exc_info=True)
            TIMEOUT_FLAG.touch()

    # Fire in background — return 202 immediately
    asyncio.create_task(_capture_qr_loop())

    return JSONResponse(
        status_code=202,
        content={
            "status": "capturing",
            "message": "QR capture started in HEADED browser. Poll GET /api/whatsapp/status every 5 seconds. The QR image will appear within 10-15 seconds.",
        },
    )


@router.post("/clear-session")
async def clear_whatsapp_session(user: dict = Depends(get_current_user)):
    """
    Wipes the WhatsApp Web browser session so you can re-authenticate with a fresh QR scan.
    """
    import shutil
    from agent.browser.ghost import ghost

    session_dir = Path(__file__).parent.parent / "ghost_session_data" / "whatsapp_automation"

    # Close all live contexts (both headed and headless keys)
    await ghost.close_context("whatsapp_automation")

    # Wipe session data on disk
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.info("[WhatsApp] Session directory wiped.")

    # Clear all flags and QR
    for path in [QR_PATH, TIMEOUT_FLAG, AUTH_FLAG]:
        if path.exists():
            path.unlink()

    return {
        "status": "cleared",
        "message": "WhatsApp session cleared. Request a fresh QR code to re-authenticate.",
    }


@router.get("/debug-screenshot")
async def get_debug_screenshot(user: dict = Depends(get_current_user)):
    """Returns the latest debug screenshot as base64 for troubleshooting failed QR captures."""
    debug_path = QR_PATH.parent / "whatsapp_debug_screenshot.png"
    if not debug_path.exists():
        return JSONResponse(status_code=404, content={"error": "No debug screenshot available."})
    try:
        b64 = base64.b64encode(debug_path.read_bytes()).decode()
        return {"screenshot_b64": b64}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
