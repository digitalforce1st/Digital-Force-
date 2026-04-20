"""
Digital Force — Deep ReAct Browser Toolkit
A set of modular, stateful tools that grant the LLM physical control over the Ghost Browser session.
"""

import asyncio
import base64
import logging
from langchain_core.tools import tool
from config import get_settings

logger = logging.getLogger(__name__)

async def _get_active_page():
    from agent.browser.ghost import ghost
    if not ghost.is_running:
        return None
    page = await ghost.get_page(account_id="research_agent")
    return page

@tool
async def ghost_goto(url: str) -> str:
    """Navigate the headless browser to a specific URL."""
    try:
        page = await _get_active_page()
        if not page:
            return "Fatal: Ghost browser is down. Cannot navigate."
        logger.info(f"[Ghost] Navigating to {url}")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2) # Stabilize DOM
        return f"Successfully navigated to {url}. The page is loaded."
    except Exception as e:
        logger.error(f"Ghost Goto Error: {e}")
        return f"Error navigating to {url}: {e}"

@tool
async def ghost_scroll(amount_pixels: int) -> str:
    """Scroll the headless browser viewport down (positive) or up (negative) by the given pixel amount."""
    try:
        page = await _get_active_page()
        if not page:
            return "Fatal: Ghost browser is down."
        await page.evaluate(f"window.scrollBy(0, {amount_pixels})")
        await asyncio.sleep(1)
        return f"Scrolled viewport by {amount_pixels} pixels."
    except Exception as e:
        logger.error(f"Ghost Scroll Error: {e}")
        return f"Error scrolling: {e}"

@tool
async def ghost_analyze_viewport(context_prompt: str) -> str:
    """
    Take a screenshot of the current visible page state in the browser and pass it to Llama-Vision.
    Use 'context_prompt' to tell the Vision model exactly what you are trying to find or extract from the image.
    """
    try:
        page = await _get_active_page()
        if not page:
            return "Fatal: Ghost browser is down."
            
        pic_path = "temp_react_viewport.png"
        await page.screenshot(path=pic_path)
        
        settings = get_settings()
        key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
        if not key:
            return "No Groq API key available for Vision inference."
            
        from groq import AsyncGroq
        client = AsyncGroq(api_key=key, max_retries=1)
        
        with open(pic_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            
        prompt = (f"You are the visual cortex for an autonomous web agent. Look at this browser viewport screenshot. "
                  f"Context for what to look for: {context_prompt}. "
                  "Extract any requested facts, text, trends, or button locations. BE CONCISE. Do not bold text using asterisks.")
                  
        resp = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            max_tokens=800,
            temperature=0.1
        )
        return str(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f"Ghost Analyze Error: {e}")
        return f"Error analyzing viewport: {e}"

@tool
async def ghost_click(text_or_selector: str) -> str:
    """
    Attempt to click an element on the screen using Playwright's smart selector engine.
    Pass either an exact text match (like "Sign In") or a CSS selector.
    """
    try:
        page = await _get_active_page()
        if not page:
            return "Fatal: Ghost browser is down."
            
        # Try finding by text first
        element = await page.query_selector(f"text='{text_or_selector}'")
        if element:
            await element.click()
            await asyncio.sleep(2)
            return f"Clicked element matching text '{text_or_selector}'."
            
        # Fallback to general selector
        element = await page.query_selector(text_or_selector)
        if element:
            await element.click()
            await asyncio.sleep(2)
            return f"Clicked element matching CSS '{text_or_selector}'."
            
        return f"Failed to find element matching '{text_or_selector}'."
    except Exception as e:
        logger.error(f"Ghost Click Error: {e}")
        return f"Error clicking element: {e}"
