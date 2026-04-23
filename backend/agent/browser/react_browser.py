"""
Digital Force — Deep ReAct Browser Toolkit
===========================================
Physical control tools for the Ghost Browser. These tools give the LLM
genuine "hands and eyes" — it can see the screen (vision), move the cursor,
type, click, and interact with any website exactly like a human operator.

The key design: ALL tools are account-scoped. Each account gets its own
isolated persistent browser session (cookies, login state, localStorage).
This is what enables true multi-account management without cross-contamination.

UPDATED (2.3):
- All tools now accept `account_id` arg to use the correct session
- Added ghost_type() for typing into focused elements
- Added ghost_press_key() for Enter, Tab, Escape etc.
- Added ghost_upload_file() for uploading images/videos to any post form
- Added ghost_wait_for() to wait for something to appear on screen
- Added ghost_get_page_text() to extract all visible text from the page
- ghost_analyze_viewport now uses the correct per-account page
"""

import asyncio
import base64
import logging
import os
from langchain_core.tools import tool
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def _get_page(account_id: str = "default", headless: bool = True):
    """Get the Ghost Browser page for a specific account session."""
    from agent.browser.ghost import ghost
    if not ghost.is_running:
        return None
    page = await ghost.get_page(account_id=account_id, headless=headless)
    return page


# ── NAVIGATION ────────────────────────────────────────────────────────────────

@tool
async def ghost_goto(url: str, account_id: str = "default") -> str:
    """
    Navigate the Ghost Browser session for this account to a specific URL.
    Always specify account_id so the right authenticated session is used.
    Example: ghost_goto('https://linkedin.com/feed', account_id='account_abc123')
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."
        logger.info(f"[Ghost:{account_id}] Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        title = await page.title()
        return f"Navigated to {url}. Page title: '{title}'"
    except Exception as e:
        return f"Error navigating to {url}: {e}"


# ── VISION ────────────────────────────────────────────────────────────────────

@tool
async def ghost_see(question: str, account_id: str = "default") -> str:
    """
    Take a screenshot of what the Ghost Browser currently sees for this account,
    then use Vision AI to answer your question about the page.
    Use this to find buttons, check if you're logged in, read page state, etc.
    
    Example questions:
    - "Am I logged into LinkedIn? What is the current page?"
    - "Where is the 'Start a post' or compose button on this page?"
    - "Is there an error message visible? What does it say?"
    - "Has the post been submitted successfully?"
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."

        pic_path = f"ghost_screenshot_{account_id}.png"
        await page.screenshot(path=pic_path, full_page=False)

        key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
        if not key:
            return "No Groq API key for vision."

        from groq import AsyncGroq
        client = AsyncGroq(api_key=key, max_retries=1)

        with open(pic_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        prompt = (
            "You are the eyes of an autonomous web agent remotely controlling a browser. "
            f"Answer this specific question about the current browser viewport: {question}\n\n"
            "Be precise and direct. If you can see a button, give its exact visible text. "
            "If you see a login wall, say so clearly. Do not use asterisks in your response."
        )

        resp = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]}],
            max_tokens=600,
            temperature=0.1
        )
        result = str(resp.choices[0].message.content)
        # Cleanup
        if os.path.exists(pic_path):
            os.remove(pic_path)
        return result
    except Exception as e:
        return f"Vision error: {e}"


# ── INTERACTION ───────────────────────────────────────────────────────────────

@tool
async def ghost_click(selector_or_text: str, account_id: str = "default") -> str:
    """
    Click an element in the browser. Pass either:
    - Visible text of the button/link (e.g. "Start a post", "Submit", "Sign in")
    - A CSS selector (e.g. "button[aria-label='Post']")
    - An aria-label (e.g. "[aria-label='Share']")
    
    Always use ghost_see() first to confirm the element exists before clicking.
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."

        clicked = False

        # Try by exact text
        try:
            await page.get_by_text(selector_or_text, exact=False).first.click(timeout=5000)
            clicked = True
        except Exception:
            pass

        # Try by role/aria label
        if not clicked:
            try:
                await page.locator(f'[aria-label*="{selector_or_text}"]').first.click(timeout=5000)
                clicked = True
            except Exception:
                pass

        # Try direct CSS selector
        if not clicked:
            try:
                await page.locator(selector_or_text).first.click(timeout=5000)
                clicked = True
            except Exception:
                pass

        await asyncio.sleep(2)

        if clicked:
            return f"Clicked '{selector_or_text}' successfully."
        return f"Could not find or click '{selector_or_text}'. Use ghost_see() to check the current page state."
    except Exception as e:
        return f"Click error: {e}"


@tool
async def ghost_type(text: str, account_id: str = "default", clear_first: bool = False) -> str:
    """
    Type text into the currently focused element in the browser.
    Call ghost_click() on the input/textarea first to focus it, then call this tool.
    Set clear_first=True to clear any existing text before typing.
    
    Works for: post compose boxes, login forms, search bars, comment fields — any input.
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."

        if clear_first:
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.3)

        # Use keyboard.type for natural human-like input (avoids bot detection)
        await page.keyboard.type(text, delay=25)
        await asyncio.sleep(1)
        chars = len(text)
        preview = text[:60] + "..." if len(text) > 60 else text
        return f"Typed {chars} characters: '{preview}'"
    except Exception as e:
        return f"Type error: {e}"


@tool
async def ghost_press_key(key: str, account_id: str = "default") -> str:
    """
    Press a keyboard key in the browser.
    Common values: "Enter", "Tab", "Escape", "Backspace", "Control+Enter", "ArrowDown"
    Use "Enter" to submit forms or confirm selections.
    Use "Escape" to close dialogs.
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."
        await page.keyboard.press(key)
        await asyncio.sleep(1.5)
        return f"Pressed key: '{key}'"
    except Exception as e:
        return f"Key press error: {e}"


@tool
async def ghost_upload_file(file_path: str, account_id: str = "default") -> str:
    """
    Upload a file (image, video) to the currently open file picker dialog or file input element.
    Use this after clicking an image/video attachment button that opens a file picker.
    Pass the absolute local file path to upload.
    
    Example: ghost_upload_file('/path/to/image.jpg', account_id='account_123')
    """
    try:
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"

        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."

        # Wait for any file chooser to be triggered
        async with page.expect_file_chooser(timeout=10000) as fc_info:
            await asyncio.sleep(0.5)  # Let the dialog open
        file_chooser = await fc_info.value
        await file_chooser.set_files(file_path)
        await asyncio.sleep(3)  # Wait for upload to process
        return f"Uploaded file: {os.path.basename(file_path)}"
    except Exception as e:
        return f"File upload error: {e}"


@tool
async def ghost_wait_for(description: str, account_id: str = "default", timeout_seconds: int = 15) -> str:
    """
    Wait for something to appear or change on the page, then confirm with vision.
    Use this after submitting a form to wait for a success message,
    or after clicking to wait for a dialog to appear.
    
    Example: ghost_wait_for('post success confirmation or error message', account_id='x')
    """
    try:
        await asyncio.sleep(min(timeout_seconds, 8))
        # After waiting, take a look at what happened
        result = await ghost_see.ainvoke({"question": description, "account_id": account_id})
        return f"After waiting {timeout_seconds}s: {result}"
    except Exception as e:
        return f"Wait error: {e}"


@tool
async def ghost_get_page_text(account_id: str = "default") -> str:
    """
    Extract all visible text from the current page in the browser session.
    Useful for reading post content, error messages, or page state without using vision.
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."
        text = await page.inner_text("body")
        # Trim to a reasonable length
        return text[:3000] + "..." if len(text) > 3000 else text
    except Exception as e:
        return f"Page text error: {e}"


@tool
async def ghost_scroll(amount_pixels: int, account_id: str = "default") -> str:
    """
    Scroll the browser page up (negative) or down (positive) by the given pixels.
    Use to reveal content that's off-screen, like a submit button below the fold.
    """
    try:
        page = await _get_page(account_id)
        if not page:
            return "Fatal: Ghost Browser is not running."
        await page.evaluate(f"window.scrollBy(0, {amount_pixels})")
        await asyncio.sleep(1)
        return f"Scrolled {amount_pixels}px {'down' if amount_pixels > 0 else 'up'}."
    except Exception as e:
        return f"Scroll error: {e}"


# Legacy alias (used by researcher node)
ghost_analyze_viewport = ghost_see
