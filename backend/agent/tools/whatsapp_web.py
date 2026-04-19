import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

from agent.browser.ghost import ghost

logger = logging.getLogger(__name__)

async def send_whatsapp_message(target_phone: str, message: str) -> Dict[str, Any]:
    """
    Sends a WhatsApp message via web.whatsapp.com using the ghost Playwright session.
    Automatically handles the QR scan requirement loop.
    Target phone should include country code (e.g., '1234567890').
    """
    try:
        # 1. Grab a persistent tab context for whatsapp
        page = await ghost.get_page(account_id="whatsapp_automation")
        
        # 2. Go to WhatsApp Send URL
        # The URL structure pre-fills the chat and opens it directly
        encoded_message = __import__("urllib.parse").parse.quote(message)
        url = f"https://web.whatsapp.com/send/?phone={target_phone}&text={encoded_message}&type=phone_number&app_absent=0"
        
        logger.info(f"[WhatsApp] Navigating to WhatsApp Web for {target_phone}...")
        await page.goto(url, wait_until="domcontentloaded")
        
        # 3. Handle Auth (Are we logged in?)
        # Wait up to 15 seconds to see either the QR code OR the actual chat input loading
        try:
            # We look for the main canvas (QR) or the compose box
            element = await page.wait_for_selector('canvas[aria-label="Scan me!"], div[title="Type a message"]', timeout=20000)
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            
            if tag_name == "canvas":
                # UNGATED QR FLOW
                logger.warning("[WhatsApp] Session is not authenticated. Capturing QR Code...")
                # Ensure the media directory exists
                media_dir = Path(__file__).parent.parent.parent.parent / "media" / "qr_codes"
                media_dir.mkdir(parents=True, exist_ok=True)
                
                qr_path = media_dir / "whatsapp_qr.png"
                await element.screenshot(path=str(qr_path))
                
                # Close page safely
                await page.close()
                return {
                    "status": "auth_required", 
                    "error": "WhatsApp Web is not authenticated. Please scan the QR code.",
                    "qr_path": str(qr_path)
                }
        except Exception as e:
             # Timeout mostly — meaning neither loaded or structural changes happened
             logger.warning(f"[WhatsApp] Timeout waiting for Auth/Chat state: {e}")
             
        # 4. Wait for the loading overlay to disappear
        # When hitting /send link, WhatsApp has a "Starting chat" loader
        await asyncio.sleep(5) # Give it time to render the chat context
        
        # 5. Check for invalid number modal
        invalid_modal = await page.query_selector("text='Phone number shared via url is invalid'")
        if invalid_modal:
            await page.close()
            return {"status": "error", "error": f"WhatsApp number {target_phone} is invalid or not on WhatsApp."}
            
        # 6. Click Send!
        # Since the text is pre-filled via URL, we just find the send button.
        # The best selector is the aria-label="Send"
        try:
            send_btn = await page.wait_for_selector('span[data-icon="send"]', timeout=10000)
            if send_btn:
                await send_btn.click()
                logger.info(f"[WhatsApp] Clicked send button for {target_phone}.")
                # Wait for the tick mark (to ensure it actually fired off the network request)
                await asyncio.sleep(2)
            else:
                 raise Exception("Send button not found.")
        except Exception as e:
            # Fallback: Find the text box and press Enter
            logger.warning(f"[WhatsApp] Send button click failed ({e}). Trying to press Enter in chatbox.")
            textbox = await page.wait_for_selector('div[title="Type a message"]', timeout=5000)
            await textbox.focus()
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

        await page.close()
        return {"status": "ok", "message": "WhatsApp message sent successfully via Ghost Engine."}

    except Exception as e:
        logger.error(f"[WhatsApp] Unhandled error during send: {e}", exc_info=True)
        try:
            await page.close()
        except:
            pass
        return {"status": "error", "error": str(e)}
