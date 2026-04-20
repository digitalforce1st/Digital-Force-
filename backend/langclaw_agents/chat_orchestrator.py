"""
Digital Force 2.0 — LangClaw Streaming Chat Orchestrator
=========================================================
A fully transparent ReAct loop that yields structured SSE events for every
cognitive step: thinking, tool calls (actions), tool results (observations),
and final answer tokens. This powers the live Thought→Action→Observation UI.
"""

import logging
import asyncio
import json
import uuid
from typing import Optional, AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage

logger = logging.getLogger(__name__)


async def stream_chat_agent(
    user_id: str,
    message: str,
    goal_id: Optional[str] = None,
    requires_workflow: bool = False,
) -> AsyncGenerator[dict, None]:
    """
    Core streaming ReAct generator. Yields structured event dicts:
      { "type": "thinking",    "content": "..." }  — internal reasoning
      { "type": "action",      "content": "...", "tool": "...", "args": {...} }
      { "type": "observation", "content": "..." }  — tool result
      { "type": "token",       "content": "..." }  — final answer token (streaming)
      { "type": "done" }
      { "type": "error",       "content": "..." }
    """
    from database import async_session, ChatMessage, AgentLog
    from sqlalchemy import select, desc
    from agent.tools.system_tools import get_agent_tools
    from agent.llm import get_tool_llm

    logger.info(f"[StreamOrchestrator] Starting for user {user_id[:8]}...")

    # ── Route to campaign workflow if needed ─────────────────────────────────
    if requires_workflow and goal_id:
        yield {"type": "thinking", "content": "User intent requires activating the full Campaign Orchestration pipeline. Routing to the primary workflow engine now..."}
        from langclaw_agents.orchestrator_app import run_orchestration
        async with async_session() as db:
            db.add(AgentLog(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                agent="orchestrator",
                level="info",
                thought="Chat intent routed to main Campaign Workflow"
            ))
            await db.commit()
        asyncio.create_task(run_orchestration(goal_id, trigger_source="chat"))
        yield {"type": "action", "content": "Campaign Orchestrator activated in background", "tool": "orchestrator_app", "args": {"goal_id": goal_id}}
        yield {"type": "done"}
        return

    # ── Build conversation history ────────────────────────────────────────────
    async with async_session() as db:
        hist_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(desc(ChatMessage.created_at)).limit(10)
        )
        hist = hist_result.scalars().all()
        messages = []
        for m in reversed(hist):
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(content=message))

    system_prompt = """You are the **Digital Force Omniscient Hub** — the central intelligence of an autonomous social media marketing agency.

You have access to tools that let you: execute Python code, query the knowledge base, read the system database, and more.

When reasoning, think step by step before calling a tool. When you call a tool, be explicit about why.
After receiving a tool result, synthesize it into your final answer.

Rules:
- Always think before acting.  
- After tool results, synthesize a concise, expert final answer.
- Never use `push_to_chat` — your final AIMessage is delivered automatically.
- Be direct, confident, and enterprise-grade in tone.
- IMPORTANT: DO NOT use markdown asterisks (`*` or `**`) to bold text anywhere in your output. Return plain text without formatting symbols.
"""
    messages.insert(0, SystemMessage(content=system_prompt))

    mock_state = {
        "created_by": user_id,
        "goal_id": goal_id,
        "platforms": [], "success_metrics": {}, "constraints": {},
        "asset_ids": [], "messages": [], "research_findings": {},
    }
    tools = get_agent_tools(mock_state)
    tool_map = {t.name: t for t in tools}
    llm = get_tool_llm(temperature=0.2).bind_tools(tools)

    max_loops = 5
    loops = 0
    tools_used = False
    final_answer = ""

    while loops < max_loops:
        loops += 1

        # ── Stream the LLM's thinking/response ───────────────────────────────
        accumulated_content = ""
        tool_calls_buffer = []

        try:
            async for chunk in llm.astream(messages):
                # Accumulate text content (the model "thinking out loud" before tool calls)
                if chunk.content:
                    if isinstance(chunk.content, str):
                        accumulated_content += chunk.content
                    elif isinstance(chunk.content, list):
                        for part in chunk.content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                accumulated_content += part.get("text", "")

                # Accumulate tool calls
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        # Merge chunks into existing tool call or create new one
                        idx = tc_chunk.get("index", 0)
                        while len(tool_calls_buffer) <= idx:
                            tool_calls_buffer.append({"id": "", "name": "", "args_str": ""})
                        if tc_chunk.get("id"):
                            tool_calls_buffer[idx]["id"] = tc_chunk["id"]
                        if tc_chunk.get("name"):
                            tool_calls_buffer[idx]["name"] = tc_chunk["name"]
                        if tc_chunk.get("args"):
                            tool_calls_buffer[idx]["args_str"] += tc_chunk["args"]

        except Exception as e:
            yield {"type": "error", "content": f"LLM stream error: {e}"}
            return

        # ── Emit the model's textual reasoning as a thinking event ───────────
        if accumulated_content.strip():
            if tool_calls_buffer:
                # This is pre-tool reasoning — emit as thinking
                yield {"type": "thinking", "content": accumulated_content.strip()}
            else:
                # This is the final answer — stream it token by token
                final_answer = accumulated_content
                for i in range(0, len(final_answer), 4):
                    yield {"type": "token", "content": final_answer[i:i+4]}
                    await asyncio.sleep(0.008)

        # ── Build the full AIMessage to append to context ────────────────────
        # Parse tool calls from buffer
        parsed_tool_calls = []
        for tc in tool_calls_buffer:
            if tc["name"]:
                try:
                    args = json.loads(tc["args_str"]) if tc["args_str"] else {}
                except json.JSONDecodeError:
                    args = {"raw": tc["args_str"]}
                parsed_tool_calls.append({
                    "id": tc["id"] or str(uuid.uuid4()),
                    "name": tc["name"],
                    "args": args,
                    "type": "tool_call"
                })

        # Append full response to message history
        ai_msg = AIMessage(
            content=accumulated_content,
            tool_calls=parsed_tool_calls if parsed_tool_calls else [],
        )
        messages.append(ai_msg)

        # ── If no tool calls, we're done ─────────────────────────────────────
        if not parsed_tool_calls:
            break

        # ── Execute each tool call ────────────────────────────────────────────
        tools_used = True
        for tc in parsed_tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]

            # Emit action event
            args_preview = json.dumps(tool_args, ensure_ascii=False)
            if len(args_preview) > 200:
                args_preview = args_preview[:200] + "..."
            yield {
                "type": "action",
                "tool": tool_name,
                "content": f"Executing `{tool_name}`",
                "args": tool_args,
                "args_preview": args_preview,
            }

            # Execute the tool
            tool_fn = tool_map.get(tool_name)
            if tool_fn:
                try:
                    result = await tool_fn.ainvoke(tool_args)
                    result_str = str(result)

                    # Log to DB
                    async with async_session() as db:
                        db.add(AgentLog(
                            id=str(uuid.uuid4()),
                            goal_id=goal_id,
                            agent="executive",
                            level="action",
                            thought=f"Tool call: {tool_name}",
                            action=tool_name,
                            observation=result_str[:500] + "..." if len(result_str) > 500 else result_str
                        ))
                        await db.commit()

                    # Emit observation
                    obs_preview = result_str[:600] + ("..." if len(result_str) > 600 else "")
                    yield {"type": "observation", "tool": tool_name, "content": obs_preview}
                    messages.append(ToolMessage(content=result_str, tool_call_id=tool_id))

                except Exception as e:
                    err = f"Tool error: {e}"
                    yield {"type": "observation", "tool": tool_name, "content": err}
                    messages.append(ToolMessage(content=err, tool_call_id=tool_id))
            else:
                msg = f"Tool `{tool_name}` not found."
                yield {"type": "observation", "tool": tool_name, "content": msg}
                messages.append(ToolMessage(content=msg, tool_call_id=tool_id))

    # ── Persist the final answer ──────────────────────────────────────────────
    if final_answer:
        async with async_session() as db:
            db.add(ChatMessage(
                id=str(uuid.uuid4()),
                user_id=user_id,
                role="agent",
                agent_name="executive - hub",
                content=final_answer,
                goal_id=goal_id
            ))
            await db.commit()

    logger.info(f"[StreamOrchestrator] Complete. Loops: {loops}, Tools used: {tools_used}")
    yield {"type": "done"}
