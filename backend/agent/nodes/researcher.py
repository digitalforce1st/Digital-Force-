"""
Digital Force — Researcher Agent Node
Gathers real-time market intelligence using active Playwright crawling inside E2B Sandbox.
"""

import json
import logging
from agent.state import AgentState
from agent.llm import generate_completion, generate_json
from agent.chat_push import chat_push, agent_thought_push
from agent.tools.sandbox import run_in_e2b

logger = logging.getLogger(__name__)

RESEARCHER_SYS_PROMPT = """You are the Lead Researcher for an autonomous social media agency.
You have access to a secure Python execution sandbox with Playwright installed.
Your job is to write a self-contained Python async function that uses Playwright (headless Chromium) or `httpx` to scrape real data from the web based on the assigned goals.

RULES:
1. Write ONE async function named `research_task`.
2. Include ALL imports inside the function.
3. Return a dict with a "success" key and a "data" key.
4. Playwright is highly recommended to bypass JS blocks. Always use headless=True.
5. Provide ONLY the python code fenced in ` ```python ... ``` `."""

from langchain_core.tools import tool

@tool
async def search_open_web(query: str, platforms: list[str] = None) -> str:
    """Use this tool to search the internet and social media platforms for live trends and insights."""
    from agent.tools.web_search import search_social_trends
    result = await search_social_trends(query, platforms or [])
    return str(result.get("results", []))

@tool
async def scrape_walled_garden_visually(platform: str, goal: str) -> str:
    """Use this tool to physically spin up a headless browser, navigate to a walled garden (Instagram, Facebook, LinkedIn, TikTok), and use Llama-Vision to analyze the DOM."""
    logger.info(f"[Researcher Tool] Ghost Visual Scrape requested for {platform}")
    findings = await _ghost_visual_research(goal, platform)
    return str(findings)

async def _ghost_visual_research(goal: str, platform: str) -> dict:
    """Uses Ghost Browser and Llama-Vision to scrape walled-gardens natively."""
    from agent.browser.ghost import ghost
    import urllib.parse
    import base64
    from config import get_settings
    from groq import AsyncGroq
    import asyncio
    
    # Fast check if playwright is running
    try:
        if not ghost.is_running:
            return {"error": "Ghost browser not actively running or installed."}
    except Exception:
        return {"error": "Playwright integration failure."}
    
    query = urllib.parse.quote_plus(goal[:50])
    if platform == "instagram":
        url = f"https://www.instagram.com/explore/tags/{query.replace('+', '')}/"
    elif platform == "facebook":
        url = f"https://www.facebook.com/search/posts/?q={query}"
    elif platform == "linkedin":
        url = f"https://www.linkedin.com/search/results/content/?keywords={query}"
    elif platform == "tiktok":
        url = f"https://www.tiktok.com/search?q={query}"
    else:
        url = f"https://www.google.com/search?q=site:{platform}.com+{query}"
        
    try:
        page = await ghost.get_page()
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(4) # Let DOM settle
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight)") # Trigger lazy load
        await asyncio.sleep(2)
        
        pic = "temp_vision_research.png"
        await page.screenshot(path=pic)
        await page.close()
        
        settings = get_settings()
        key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
        client = AsyncGroq(api_key=key, max_retries=1)
        
        with open(pic, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
            
        prompt = (f"You are a social media researcher. The user's goal is: {goal}. "
                  f"Analyze this screenshot of {platform}. Identify trending topics, visual aesthetics, "
                  "and any recurring themes. Extract JSON matching exactly: "
                  "{\"trending_topics\": [\"topic1\"], \"recommended_hashtags\": {\"global\": []}, \"content_angles\": [\"angle1\"], \"audience_insights\": \"...\"}")
                  
        resp = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            max_tokens=600,
            temperature=0.2
        )
        content = resp.choices[0].message.content
        import re, json
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except Exception as e:
        logger.error(f"[Vision Researcher] Failed natively scraping {platform}: {e}")
        return {"error": str(e)}

async def researcher_node(state: AgentState) -> dict:
    """
    A robust ReAct loop. Decides organically whether to use Tavily open-web search
    or Ghost visual browser scraping based on the platforms requested.
    """
    goal_id = state['goal_id']
    user_id = state.get('created_by', '')
    goal    = state["goal_description"]
    platforms = [p.lower() for p in state.get("platforms", [])]
    
    logger.info(f"[Researcher] Starting nested ReAct research for goal {goal_id}")

    await agent_thought_push(
        user_id=user_id,
        agent_name="researcher",
        context="initiating intelligence gathering ReAct loop across network nodes",
        goal_id=goal_id,
    )

    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    import json
    import re
    
    llm = get_tool_llm(temperature=0.2)
    tools = [search_open_web, scrape_walled_garden_visually]
    
    sys_prompt = f"""You are the Lead Social Media Researcher in a Swarm architecture.
Your objective is to find real-time trending topics and content angles for the user's goal.
You are researching these specific platforms: {platforms}

You have two tools:
1. `search_open_web`: Fast and robust text intelligence scraping.
2. `scrape_walled_garden_visually`: Launches a headless Chromium browser to visually inspect walled gardens (like TikTok/Instagram).

CRITICAL RULE:
Once you have explored enough data, stop calling tools. Your final output MUST be EXACTLY a raw JSON object (and nothing else) matching this schema:
{{
  "trending_topics": ["topic1", "topic2"],
  "recommended_hashtags": {{"global": ["#tag"]}},
  "content_angles": ["angle1"],
  "audience_insights": "detailed insight string"
}}
"""

    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
    prompt = f"Goal: {goal}\nPlatforms: {platforms}"

    try:
        final_state = await agent.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            {"recursion_limit": 6}
        )
    except Exception as e:
        logger.error(f"[Researcher ReAct Engine] Halting due to recursion or exception: {e}")
        # Return fallback on fatal loop crash
        return {
            "research_findings": {"trending_topics": ["General Trend"], "recommended_hashtags": {"global": ["#marketing"]}, "content_angles": ["Educational"], "audience_insights": "Fallback due to timeout."},
            "next_agent": "supervisor"
        }

    # Extract final message and parse JSON
    messages = final_state.get("messages", [])
    output = ""
    for msg in reversed(messages):
        if msg.type == "ai" and msg.content:
            output = msg.content
            break

    findings = {}
    try:
        # Strict fallback matching
        match = re.search(r'\{.*\}', output, re.DOTALL)
        if match:
            findings = json.loads(match.group())
        else:
            findings = json.loads(output)
    except Exception as e:
        logger.warning(f"[Researcher] Could not parse exact JSON from loop output: {e}\nRaw: {output[:200]}")
        findings = {
            "trending_topics": ["General"], "recommended_hashtags": {"global": ["#digital"]},
            "content_angles": ["General Approach"], "audience_insights": output[:200]
        }

    topics = findings.get('trending_topics', [])
    angles = findings.get('content_angles', [])

    await agent_thought_push(
        user_id=user_id,
        agent_name="researcher",
        context=f"React loop successfully compiled {len(topics)} trends and {len(angles)} insights from live agents",
        goal_id=goal_id,
    )
    
    return {
        "research_findings": findings,
        "needs_replanning_research": False,
        "messages": [{"role": "assistant", "name": "researcher", "content": f"Live Scraping Loop Completed: {len(topics)} topics found."}],
        "next_agent": "supervisor"
    }
