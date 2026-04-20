"""
Digital Force — Content Director Agent Node
Writes platform-optimized social media content using brand RAG context.
Persona is loaded dynamically from skills/content_director_skill.md.
"""

import json
import logging
from pathlib import Path
from agent.state import AgentState
from agent.llm import generate_completion, generate_json
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Load Persona from Markdown Skill File (Prompt-as-Code) ────────────────────
_SKILL_FILE = Path(__file__).parent.parent.parent / "skills" / "content_director_skill.md"
_CONTENT_DIRECTOR_SKILL = _SKILL_FILE.read_text() if _SKILL_FILE.exists() else "You are an elite social media copywriter."

from langchain_core.tools import tool

@tool
async def search_brand_voice(platform: str, topic: str) -> str:
    """Query the Brand Memory RAG store to fetch past successful content, brand rules, and tone guidelines for the given platform."""
    try:
        from rag.retriever import retrieve
        results = await retrieve(query=f"{platform} content: {topic}", collection="brand", top_k=3)
        if results:
            return "\n".join([r.get("text", "") for r in results])
        return "No brand history available for this topic. Use a professional, authoritative, inspiring voice."
    except Exception as e:
        logger.warning(f"RAG retrieval failed: {e}")
        return "RAG Unavailable. Assume professional tone."

@tool
async def determine_platform_rules(platform: str) -> str:
    """Identify the CURRENT optimal algorithm constraints, hashtag limits, and format tips for a specific platform."""
    system = "You are an elite platform algorithm expert. Return optimal formatting rules."
    prompt = f"Target Platform: {platform}. Return concise rules for chars, hashtags, and hooks."
    try:
        rules = await generate_completion(prompt, system, temperature=0.1)
        return rules
    except Exception as e:
        return "Optimal: 150-300 chars, 3 hashtags, strong hook."


async def content_director_node(state: AgentState) -> dict:
    """
    Processes the current task's content brief and writes platform-optimized content
    via an internal ReAct loop that fetches context dynamically.
    """
    tasks = state.get("tasks", [])
    completed = state.get("completed_task_ids", [])
    current_id = state.get("current_task_id")
    
    # ── Map-Reduce Execution Targeting ──
    if current_id:
        pending_task = next((t for t in tasks if t.get("id") == current_id), None)
    else:
        pending_task = next(
            (t for t in tasks if t.get("task_type") == "generate_content" and t.get("id") not in completed),
            None
        )

    if not pending_task:
        return {"next_agent": "publisher", "messages": [{"role": "assistant", "name": "content_director", "content": "All content tasks complete."}]}

    platform = pending_task.get("platform", "linkedin")
    brief = pending_task.get("content_brief", {})

    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    import re
    
    llm = get_tool_llm(temperature=0.3)
    tools = [search_brand_voice, determine_platform_rules]
    
    sys_prompt = f"""You are the Elite Content Director of the swarm.
{_CONTENT_DIRECTOR_SKILL}

You must write content for exactly one task. First, use your tools to understand the Brand Voice and the {platform} formatting rules.
Once you have the context you need, stop using tools and output EXACTLY a JSON document matching this schema:
{{
  "hook": "The first 3 words to capture attention",
  "body": "The main content formatted correctly",
  "call_to_action": "The engagement prompt",
  "hashtags": ["#tag1", "#tag2"],
  "media_instructions": "What visual should accompany this"
}}
DO NOT wrap the final JSON in markdown.
"""

    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
    
    user_prompt = f"""
CAMPAIGN: {state.get('campaign_plan', {}).get('campaign_name', 'Campaign')}
TASK: {pending_task.get('description')}
KEY MESSAGE: {brief.get('key_message', state.get('goal_description', ''))}
CONTENT TYPE: {brief.get('content_type', 'thought_leadership')}
PLATFORM: {platform}
RESEARCH CONTEXT: {json.dumps(state.get('research_findings', {}).get('content_angles', [])[:2])}
"""

    try:
        final_state = await agent.ainvoke({"messages": [HumanMessage(content=user_prompt)]}, {"recursion_limit": 5})
    except Exception as e:
        logger.error(f"[ContentDirector ReAct] Crashed: {e}")
        return {"error": str(e), "next_agent": "orchestrator"}

    messages = final_state.get("messages", [])
    output = ""
    for msg in reversed(messages):
        if msg.type == "ai" and msg.content:
            output = msg.content
            break

    try:
        match = re.search(r'\{.*\}', output, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = json.loads(output)
            
        result["platform"] = platform
        result["task_id"] = pending_task.get("id", "")

        logger.info(f"[ContentDirector] Generated content via ReAct: {result.get('hook', '')[:50]}...")

        # Mutate the active task queue so it is ready for publishing
        new_tasks = []
        for t in tasks:
            if t.get("id") == pending_task.get("id"):
                t["result"] = result
                t["task_type"] = "post_content"
            new_tasks.append(t)

        return {
            "messages": [{"role": "assistant", "name": "content_director", "content": f"Content drafted for {platform}: {result.get('hook', '')[:60]}..."}],
            "content_swarm_results": [{"task_id": pending_task.get("id", ""), "result": result}], 
            "next_agent": "orchestrator", # Replaced legacy visual_designer
            "current_task_id": pending_task.get("id"),
        }

    except Exception as e:
        logger.error(f"[ContentDirector] Error parsing ReAct output: {e}\nRaw: {output[:200]}")
        return {
            "error": str(e),
            "next_agent": "orchestrator", 
        }
