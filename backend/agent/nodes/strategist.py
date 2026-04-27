"""
Digital Force — Strategist Agent Node
Creates full campaign plans from mission briefs + research.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from agent.state import AgentState
from agent.llm import generate_json
from agent.chat_push import chat_push, agent_thought_push

logger = logging.getLogger(__name__)

_PROMPT = (Path(__file__).parent.parent / "prompts" / "strategist.md").read_text()

from langchain_core.tools import tool

@tool
async def search_episodic_memories(query: str) -> str:
    """Retrieve strategic insights, lessons learned, and past campaign failures from the Episodic Memory database."""
    try:
        from rag.retriever import retrieve
        memory_results = await retrieve(
            query=query, 
            collection="knowledge", 
            top_k=3,
            filter_metadata={"category": "episodic_memory"}
        )
        memories = [m["text"] for m in memory_results]
        return "\n".join([f"- {m}" for m in memories]) if memories else "No past lessons for this topic."
    except Exception as e:
        return f"Episodic memory unavailable: {e}"

async def strategist_node(state: AgentState) -> dict:
    """
    Takes the parsed goal + research findings, produces a full campaign plan
    via a ReAct loop to iteratively consult memory before planning.
    """
    goal_id = state['goal_id']
    user_id = state.get('created_by', '')
    logger.info(f"[Strategist] Terminating procedural path. Booting ReAct Strategist for goal {goal_id}")

    await agent_thought_push(
        user_id=user_id,
        context="synthesizing research through iterative memory retrieval ReAct loop",
        agent_name="strategist",
        goal_id=goal_id,
    )

    deadline = state.get("deadline") or (datetime.utcnow() + timedelta(days=7)).isoformat()
    research = state.get("research_findings", {})

    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    import re
    
    llm = get_tool_llm(temperature=0.3)
    tools = [search_episodic_memories]

    sys_prompt = f"""You are the Master Strategist of this autonomous social media agency.
Your objective is to build a massive, highly-detailed multi-platform campaign plan.
You MUST search the episodic memory using your `search_episodic_memories` tool before writing the plan so you don't repeat past failures.

Once you have consulted memory, stop using tools and output EXACTLY a JSON document matching this schema:
{{
  "campaign_name": "String",
  "duration_days": 7,
  "tasks": [
    {{
      "id": "task_1",
      "task_type": "generate_content",
      "platform": "linkedin",
      "description": "Write a thought-leadership post.",
      "content_brief": {{"key_message": "...", "tone": "...", "content_type": "text"}}
    }}
  ],
  "reasoning": "Explain why this strategy works and how it avoids past mistakes."
}}
DO NOT wrap the final JSON in markdown.
"""

    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
    
    prompt = f"""
MISSION:
- Goal: {state['goal_description']}
- Platforms: {state.get('platforms', [])}
- Deadline: {deadline}
- Success Metrics: {json.dumps(state.get('success_metrics', {}))}
- Constraints: {json.dumps(state.get('constraints', {}))}
- Media Assets: {state.get('asset_ids', [])}

RESEARCH FINDINGS:
{json.dumps(research, indent=2) if research else 'None.'}
"""

    try:
        final_state = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]}, {"recursion_limit": 5})
        messages = final_state.get("messages", [])
        output = ""
        for msg in reversed(messages):
            if msg.type == "ai" and msg.content:
                output = msg.content
                break

        # Strict fallback matching
        match = re.search(r'\{.*\}', output, re.DOTALL)
        if match:
            plan = json.loads(match.group())
        else:
            plan = json.loads(output)
            
        tasks = plan.get("tasks", [])
        duration = plan.get('duration_days', 7)
        logger.info(f"[Strategist] Generated ReAct plan with {len(tasks)} tasks")

        await agent_thought_push(
            user_id=user_id,
            context=f"finalized the entire campaign strategy consisting of {len(tasks)} tasks after consulting episodic past records",
            agent_name="strategist",
            goal_id=goal_id,
            metadata={"task_count": len(tasks), "duration_days": duration},
        )

        return {
            "campaign_plan": plan,
            "tasks": tasks,
            "messages": [{"role": "assistant", "name": "strategist", "content": f"Plan created: {len(tasks)} tasks"}],
            "next_agent": "orchestrator",
        }
    except Exception as e:
        logger.error(f"[Strategist] ReAct or Parse Error: {e}. Falling back to synthetic plan generation.")
        
        # SYNTHETIC FALLBACK PLAN: Ensures the orchestrator loop NEVER stalls due to an LLM crash.
        fallback_tasks = []
        platforms = state.get("platforms") or ["linkedin"]
        for idx, plat in enumerate(platforms):
            fallback_tasks.append({
                "id": f"task_fallback_{idx}",
                "task_type": "generate_content",
                "platform": plat,
                "description": f"Create standard content for {plat}",
                "content_brief": {"key_message": state.get("goal_description", "Standard campaign execution"), "tone": "professional"}
            })
            
        fallback_plan = {
            "campaign_name": "Emergency Fallback Plan",
            "duration_days": 7,
            "tasks": fallback_tasks,
            "reasoning": "Standard execution generated due to strategic analysis node failure."
        }
        
        await agent_thought_push(
            user_id=user_id,
            context="research tools unavailable, generated synthesized baseline campaign tasks",
            agent_name="strategist",
            goal_id=goal_id,
        )

        return {
            "campaign_plan": fallback_plan,
            "tasks": fallback_tasks,
            "messages": [{"role": "assistant", "name": "strategist", "content": f"Fallback Plan created: {len(fallback_tasks)} tasks"}],
            "next_agent": "orchestrator",
        }
