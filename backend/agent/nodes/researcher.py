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

from agent.browser.react_browser import ghost_goto, ghost_scroll, ghost_analyze_viewport, ghost_click

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
    tools = [search_open_web, ghost_goto, ghost_scroll, ghost_analyze_viewport, ghost_click]
    
    sys_prompt = f"""You are the Lead Social Media Researcher in a Swarm architecture.
Your objective is to find real-time trending topics and content angles for the user's goal.
You are researching these specific platforms: {platforms}

You have access to standard web search, AND a Deep ReAct Ghost Browser.
If researching a "walled garden" (Instagram, LinkedIn, Facebook, TikTok), you MUST use the physical browser tools:
1. Use `ghost_goto` to navigate to a search URL (e.g. https://www.tiktok.com/search?q=xyz).
2. Use `ghost_analyze_viewport` to see the current page structure via Llama-Vision.
3. If no content is loaded, use `ghost_click` or `ghost_scroll` to navigate further, then analyze again.

CRITICAL RULE:
Once you have explored enough data across your tools, stop calling tools. Your final output MUST be EXACTLY a raw JSON object (and nothing else) matching this schema:
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
            {"recursion_limit": 15}
        )
    except Exception as e:
        logger.error(f"[Researcher ReAct Engine] Halting due to recursion or exception: {e}")
        raise RuntimeError(f"Live research failed: {e}")

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
        raise ValueError(f"Failed to parse research data output: {e}")

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
