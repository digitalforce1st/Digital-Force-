"""
Digital Force 2.0 — LangClaw Chat God-Node
==========================================
Replaces the old bloated `manager_node.py` and `graph.py` for chat interactions.
Instead of passing huge `AgentState` dictionaries, this simply reads tools,
executes a ReAct loop if necessary (for web_search, sandbox python execution, etc.),
and saves thoughts/actions directly to the Postgres `AgentLog` and `ChatMessage` tables.
"""

import logging
import asyncio
import json
import uuid
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage

logger = logging.getLogger(__name__)

async def run_chat_agent(user_id: str, message: str, goal_id: Optional[str] = None, requires_workflow: bool = False):
    """
    The background ReAct loop for ad-hoc chat requests.
    If requires_workflow is True, it will also trigger the primary campaign orchestrated.
    """
    from database import async_session, ChatMessage, AgentLog
    from sqlalchemy import select, desc
    from agent.tools.system_tools import get_agent_tools
    from agent.llm import get_tool_llm
    from agent.chat_push import chat_push
    
    logger.info(f"[ChatOrchestrator] Waking up for user {user_id[:8]}...")

    # If the user's intent is actually to run the campaign workflow (strategize, publish, etc.)
    # we just route it directly to the orchestrator_app.
    if requires_workflow and goal_id:
        from langclaw_agents.orchestrator_app import run_orchestration
        
        # Log that we are handing off
        async with async_session() as db:
            db.add(AgentLog(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                agent="orchestrator",
                level="info",
                thought="Chat Intent routed to main Campaign Workflow"
            ))
            await db.commit()
            
        logger.info("[ChatOrchestrator] Delegating to main Campaign Orchestrator Hub")
        await run_orchestration(goal_id, trigger_source="chat")
        return

    # Otherwise, this is a Native ReAct Chat sequence (e.g. user asked for a web search, python script, or analytics pull).
    
    # 1. Fetch slim chat history
    async with async_session() as db:
        hist_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(desc(ChatMessage.created_at)).limit(8)
        )
        hist = hist_result.scalars().all()
        # Convert to Langchain messages
        messages = []
        for m in reversed(hist):
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

    # Fallback if no history was found (shouldn't happen since chat.py saves it first)
    if not messages or getattr(messages[-1], "type", "") != "human":
        messages.append(HumanMessage(content=message))

    system_prompt = """You are the **Omniscient ReAct God-Node** of the Digital Force AI Agency.
You have native ability to write code, read the database, query memory, or browse the web.
You use Tools to fulfill the user's request. 

If the user gives you a password, auth token, or credential, immediately use `update_truth_bucket` to save it!
If the user wants you to extract data, parse files, or do non-social-media tasks, use `execute_python` and write a robust python script to do it in the local sandbox!
Otherwise, use `web_search` or whatever is appropriate.

When using a tool, explicitly output your reasoning. Once you have a final answer from the tools, DO NOT use `push_to_chat` (because your final AIMessage will be sent back naturally). Just return the final answer.
"""
    messages.insert(0, SystemMessage(content=system_prompt))
    
    # Needs a mock state to get tools
    mock_state = {
        "created_by": user_id, 
        "goal_id": goal_id,
        "platforms": [], "success_metrics": {}, "constraints": {},
        "asset_ids": [], "messages": [], "research_findings": {},
    }
    tools = get_agent_tools(mock_state)
    llm = get_tool_llm(temperature=0.2).bind_tools(tools)
    
    max_loops = 4
    loops = 0
    tools_used = False
    
    while loops < max_loops:
        loops += 1
        response = await llm.ainvoke(messages)
        messages.append(response)
        
        if not response.tool_calls:
            # We have our final text answer. 
            if tools_used: 
                # We only push a followup chat if we actually DID something in the background, 
                # because chat.py already streamed an immediate conversational response for the first prompt.
                await chat_push(user_id, response.content, "executive - hub", goal_id)
            break
            
        tools_used = True
        
        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            logger.info(f"[ChatOrchestrator] Executing tool: {tool_name}")
            
            # Find tool
            tool_func = next((t for t in tools if t.name == tool_name), None)
            if tool_func:
                try:
                    res = await tool_func.ainvoke(tool_args)
                    res_str = str(res)
                    messages.append(ToolMessage(content=res_str, tool_call_id=tc["id"]))
                    
                    # Store action visually in the logs so frontend sees it
                    async with async_session() as db:
                        db.add(AgentLog(
                            id=str(uuid.uuid4()),
                            goal_id=goal_id,
                            agent="executive",
                            level="action",
                            thought=f"Executing {tool_name} from chat directive",
                            action=tool_name,
                            observation=res_str[:500] + "..." if len(res_str) > 500 else res_str
                        ))
                        await db.commit()
                        
                except Exception as e:
                    messages.append(ToolMessage(content=f"Error: {e}", tool_call_id=tc["id"]))
            else:
                messages.append(ToolMessage(content="Tool not found.", tool_call_id=tc["id"]))

    logger.info("[ChatOrchestrator] Native Chat Execution Complete.")
