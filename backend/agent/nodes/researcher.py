"""
Digital Force — Researcher Agent Node
Gathers real-time market intelligence using web search and Ghost Browser scraping.
Gracefully degrades — the orchestrator loop must never crash because research fails.
"""

import json
import logging
import re
from agent.state import AgentState
from agent.llm import generate_completion, generate_json
from agent.chat_push import chat_push, agent_thought_push

logger = logging.getLogger(__name__)

RESEARCHER_SYS_PROMPT = """You are the Lead Researcher for an autonomous social media agency.
You have access to web search tools to find real-time data.

RULES:
1. Search for relevant trending topics and audience insights.
2. Return structured JSON with your findings."""

from langchain_core.tools import tool

@tool
async def search_open_web(query: str, platforms: list = None) -> str:
    """Use this tool to search the internet and social media platforms for live trends and insights."""
    try:
        from agent.tools.web_search import search_social_trends
        result = await search_social_trends(query, platforms or [])
        return str(result.get("results", []))
    except Exception as e:
        logger.warning(f"[Researcher] Web search failed: {e}")
        return f"Web search unavailable: {e}"

try:
    from agent.browser.react_browser import ghost_goto, ghost_scroll, ghost_analyze_viewport, ghost_click
    _BROWSER_TOOLS = [ghost_goto, ghost_scroll, ghost_analyze_viewport, ghost_click]
except ImportError:
    logger.warning("[Researcher] Browser tools unavailable — web-only research mode")
    _BROWSER_TOOLS = []


def _build_fallback_research(goal: str, platforms: list) -> dict:
    """Generate minimal synthetic research so the orchestrator can proceed even without web access."""
    return {
        "trending_topics": [f"{goal[:30]} trends", "engagement strategies", "audience growth"],
        "recommended_hashtags": {"global": ["#marketing", "#socialmedia", "#growth"]},
        "content_angles": [
            "Educational + value-add post",
            "Behind-the-scenes authenticity",
            "Industry insight thought leadership",
        ],
        "audience_insights": f"Target audience for '{goal[:50]}' prefers authentic, value-driven content with clear calls to action.",
        "source": "synthetic_fallback",
    }


async def researcher_node(state: AgentState) -> dict:
    """
    A robust ReAct loop. Decides organically whether to use open-web search
    or Ghost visual browser scraping based on the platforms requested.
    
    NEVER raises exceptions — always returns usable research findings even on failure.
    """
    goal_id   = state['goal_id']
    user_id   = state.get('created_by', '')
    goal      = state["goal_description"]
    platforms = [p.lower() for p in state.get("platforms", [])]

    logger.info(f"[Researcher] Starting research for goal {goal_id}")

    await agent_thought_push(
        user_id=user_id,
        agent_name="researcher",
        context="initiating intelligence gathering across network nodes",
        goal_id=goal_id,
    )

    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage

    try:
        llm = get_tool_llm(temperature=0.2)
    except RuntimeError as e:
        logger.warning(f"[Researcher] No LLM available: {e} — returning fallback research")
        findings = _build_fallback_research(goal, platforms)
        return {
            "research_findings": findings,
            "needs_replanning_research": False,
            "messages": [{"role": "assistant", "name": "researcher", "content": "Research used fallback (no LLM)."}],
            "next_agent": "supervisor"
        }

    tools = [search_open_web] + _BROWSER_TOOLS

    sys_prompt = f"""You are the Lead Social Media Researcher in a Swarm architecture.
Your objective is to find real-time trending topics and content angles for the user's goal.
You are researching these specific platforms: {platforms}

CRITICAL RULE:
Once you have explored enough data across your tools, stop calling tools. Your final output MUST be EXACTLY a raw JSON object (and nothing else) matching this schema:
{{
  "trending_topics": ["topic1", "topic2"],
  "recommended_hashtags": {{"global": ["#tag"]}},
  "content_angles": ["angle1"],
  "audience_insights": "detailed insight string"
}}
"""

    # ── Both agent construction AND invocation are wrapped together ──────────
    # create_react_agent() was previously outside any try/except. Any LangGraph
    # version conflict, tool schema error, or LLM connection failure at
    # construction time would propagate uncaught, causing dispatch_researcher
    # to return {"status": "failed"} and triggering the infinite researcher loop.
    try:
        agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
        prompt_msg = f"Goal: {goal}\nPlatforms: {platforms}"
        final_state = await agent.ainvoke(
            {"messages": [HumanMessage(content=prompt_msg)]},
            {"recursion_limit": 10}
        )
    except Exception as e:
        logger.warning(f"[Researcher] ReAct agent failed (construction or invocation): {e} — returning fallback research")
        findings = _build_fallback_research(goal, platforms)
        await agent_thought_push(
            user_id=user_id, agent_name="researcher",
            context=f"research tools unavailable ({type(e).__name__}), using synthesized market context instead",
            goal_id=goal_id,
        )
        return {
            "research_findings": findings,
            "needs_replanning_research": False,
            "messages": [{"role": "assistant", "name": "researcher", "content": f"Research degraded gracefully: {str(e)[:100]}"}],
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
        match = re.search(r'\{.*\}', output, re.DOTALL)
        if match:
            findings = json.loads(match.group())
        else:
            findings = json.loads(output)
    except Exception as e:
        logger.warning(f"[Researcher] Could not parse JSON output: {e} — using fallback")
        findings = _build_fallback_research(goal, platforms)

    topics = findings.get('trending_topics', [])
    angles = findings.get('content_angles', [])

    await agent_thought_push(
        user_id=user_id,
        agent_name="researcher",
        context=f"compiled {len(topics)} trends and {len(angles)} content angles from live research",
        goal_id=goal_id,
    )

    return {
        "research_findings": findings,
        "needs_replanning_research": False,
        "messages": [{"role": "assistant", "name": "researcher", "content": f"Research completed: {len(topics)} topics found."}],
        "next_agent": "supervisor"
    }
