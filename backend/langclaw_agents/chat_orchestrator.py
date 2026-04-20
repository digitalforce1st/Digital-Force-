"""
Digital Force 2.0 — LangClaw Streaming Chat Orchestrator
=========================================================
A fully transparent ReAct loop that yields structured SSE events for every
cognitive step: thinking, tool calls (actions), tool results (observations),
and final answer tokens. This powers the live Thought→Action→Observation UI.

FIXED (2.2):
- asset_ids forwarded from chat → goal creation → orchestrator
- Media assets (public URLs) injected into the system prompt so agents
  can reference real images/videos in their content plans
- accounts state now pulled across all users (not filtered by user_id) so
  accounts added in Settings > Integrations are visible
"""

import logging
import asyncio
import json
import uuid
from typing import Optional, List, AsyncGenerator
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage

logger = logging.getLogger(__name__)


async def _load_user_context(user_id: str) -> dict:
    """Load the user's platform connections, agency settings, recent goals, and media assets."""
    context = {"accounts": [], "agency": {}, "active_goals": [], "media_assets": []}
    try:
        from database import async_session, PlatformConnection, AgencySettings, Goal, MediaAsset
        from sqlalchemy import select, desc
        async with async_session() as db:
            # Load ALL platform connections (Truth Bucket accounts) — not filtered by user
            acc_res = await db.execute(
                select(PlatformConnection).where(PlatformConnection.is_enabled == True)
            )
            accounts = acc_res.scalars().all()
            context["accounts"] = [
                {
                    "platform": a.platform,
                    "label": a.account_label,
                    "display_name": a.display_name,
                    "status": a.connection_status,
                    "id": a.id,
                }
                for a in accounts
            ]

            # Load agency settings (brand voice / industry)
            cfg_res = await db.execute(select(AgencySettings).where(AgencySettings.user_id == user_id))
            cfg = cfg_res.scalar_one_or_none()
            if cfg:
                context["agency"] = {
                    "industry": cfg.industry or "",
                    "brand_voice": cfg.brand_voice or "",
                    "agent_tone": cfg.agent_tone or "",
                }

            # Load recent active goals
            goals_res = await db.execute(
                select(Goal)
                .where(Goal.created_by == user_id)
                .where(Goal.status.in_(["planning", "executing", "awaiting_approval", "monitoring"]))
                .order_by(desc(Goal.created_at)).limit(3)
            )
            goals = goals_res.scalars().all()
            context["active_goals"] = [
                {"id": g.id, "title": g.title, "status": g.status, "progress": g.progress_percent}
                for g in goals
            ]

            # Load recent media assets (last 20) so agents know what files are available
            media_res = await db.execute(
                select(MediaAsset)
                .where(MediaAsset.uploaded_by == user_id)
                .order_by(desc(MediaAsset.created_at)).limit(20)
            )
            assets = media_res.scalars().all()
            context["media_assets"] = [
                {
                    "id": a.id,
                    "filename": a.original_filename or a.filename,
                    "type": a.asset_type,
                    "public_url": a.public_url or "",
                    "ai_description": a.ai_description or "",
                }
                for a in assets
            ]

    except Exception as e:
        logger.warning(f"[ChatOrchestrator] Failed to load user context: {e}")
    return context


async def _create_goal_from_chat(
    user_id: str,
    message: str,
    platforms: list,
    asset_ids: List[str],
) -> Optional[str]:
    """Creates a new Goal in the DB with asset_ids attached, returns the goal_id."""
    try:
        from database import async_session, Goal
        goal_id = str(uuid.uuid4())
        async with async_session() as db:
            goal = Goal(
                id=goal_id,
                title=message[:100],
                description=message,
                platforms=json.dumps(platforms),
                assets=json.dumps(asset_ids),     # ← FIXED: store assets in goal
                status="planning",
                created_by=user_id,
            )
            db.add(goal)
            await db.commit()
        logger.info(f"[ChatOrchestrator] Created goal {goal_id} with {len(asset_ids)} asset(s) and platforms={platforms}")
        return goal_id
    except Exception as e:
        logger.error(f"[ChatOrchestrator] Failed to create goal from chat: {e}")
        return None


async def stream_chat_agent(
    user_id: str,
    message: str,
    goal_id: Optional[str] = None,
    requires_workflow: bool = False,
    detected_platforms: list = None,
    asset_ids: List[str] = None,
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

    asset_ids = asset_ids or []
    detected_platforms = detected_platforms or []

    logger.info(f"[StreamOrchestrator] Starting for user {user_id[:8]}... assets={asset_ids}")

    # ── Load rich user context ───────────────────────────────────────────────────
    ctx = await _load_user_context(user_id)
    accounts = ctx["accounts"]
    agency = ctx["agency"]
    active_goals = ctx["active_goals"]
    media_assets = ctx["media_assets"]

    # ── If campaign work requested: create goal and fire orchestrator ────────────
    if requires_workflow:
        yield {"type": "thinking", "content": f"Campaign intent detected with {len(asset_ids)} media asset(s) attached. Creating autonomous execution goal and activating the Orchestrator Swarm..."}

        # Use existing goal_id or create a new one
        if not goal_id:
            goal_id = await _create_goal_from_chat(user_id, message, detected_platforms, asset_ids)

        if goal_id:
            # If an existing goal was passed but assets were just attached, update it
            if asset_ids:
                try:
                    from database import async_session, Goal
                    async with async_session() as db:
                        g = await db.get(Goal, goal_id)
                        if g:
                            existing_assets = json.loads(g.assets or "[]")
                            merged = list(set(existing_assets + asset_ids))
                            g.assets = json.dumps(merged)
                            await db.commit()
                except Exception as e:
                    logger.warning(f"[ChatOrchestrator] Could not merge assets into existing goal: {e}")

            from langclaw_agents.orchestrator_app import run_orchestration
            from database import async_session, AgentLog
            async with async_session() as db:
                db.add(AgentLog(
                    id=str(uuid.uuid4()),
                    goal_id=goal_id,
                    agent="orchestrator",
                    level="info",
                    thought="Chat intent routed to main Campaign Workflow"
                ))
                await db.commit()
            # Fire orchestrator in background — non-blocking
            asyncio.create_task(run_orchestration(goal_id, trigger_source="chat"))
            yield {
                "type": "action",
                "content": "Orchestrator Swarm activated in background",
                "tool": "orchestrator_app",
                "args": {"goal_id": goal_id}
            }

            asset_note = f" Your {len(asset_ids)} attached media file(s) are included in the campaign assets." if asset_ids else ""
            platform_note = f" Targeting: {', '.join(detected_platforms)}." if detected_platforms else ""

            yield {
                "type": "token",
                "content": f"Campaign goal created and the swarm is now running autonomously. Goal ID: {goal_id[:8]}...{platform_note}{asset_note}\n\nYou can track progress in the Goals dashboard. I will update you here as agents report back."
            }
            yield {"type": "done"}

            # Save to chat history
            async with async_session() as db:
                db.add(ChatMessage(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    role="agent",
                    agent_name="orchestrator",
                    content=f"Campaign goal created and the swarm is now running autonomously. Goal ID: {goal_id[:8]}...{platform_note}{asset_note}\n\nYou can track progress in the Goals dashboard.",
                    goal_id=goal_id
                ))
                await db.commit()
            return
        else:
            yield {"type": "thinking", "content": "Could not create goal. Falling back to conversational mode."}

    # ── Build conversation history ────────────────────────────────────────────────
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

    # ── Build rich system prompt with full context injection ─────────────────────
    accounts_block = ""
    if accounts:
        lines = [
            f"  - {a['platform'].upper()} | {a['display_name']} ({a['label']}) | Status: {a['status']} | ID: {a['id']}"
            for a in accounts
        ]
        accounts_block = "MANAGED ACCOUNTS (Truth Bucket):\n" + "\n".join(lines)
    else:
        accounts_block = "MANAGED ACCOUNTS: None configured yet. Tell the user to add accounts in Settings > Integrations."

    active_goals_block = ""
    if active_goals:
        lines = [f"  - [{g['status'].upper()}] {g['title']} (ID: {g['id'][:8]}..., Progress: {g['progress']}%)" for g in active_goals]
        active_goals_block = "ACTIVE CAMPAIGNS:\n" + "\n".join(lines)
    else:
        active_goals_block = "ACTIVE CAMPAIGNS: None currently running."

    agency_block = ""
    if agency.get("industry"):
        agency_block = f"AGENCY CONTEXT:\n  Industry: {agency['industry']}\n  Brand Voice: {agency.get('brand_voice', 'Not set')}"

    # Inject media library into system prompt
    media_block = ""
    if media_assets:
        lines = [
            f"  - [{a['type'].upper()}] {a['filename']} | URL: {a['public_url']} | ID: {a['id']}"
            + (f" | AI: {a['ai_description'][:60]}..." if a['ai_description'] else "")
            for a in media_assets
        ]
        media_block = "AVAILABLE MEDIA ASSETS (agent can use these in campaigns):\n" + "\n".join(lines)
    else:
        media_block = "AVAILABLE MEDIA ASSETS: None uploaded yet."

    # Currently attached assets in this message
    attached_block = ""
    if asset_ids:
        attached_block = f"\nCURRENTLY ATTACHED ASSETS (user just selected these for this request): {asset_ids}"

    system_prompt = f"""You are the Digital Force Omniscient Hub — the central intelligence of an autonomous social media marketing agency.

{accounts_block}

{active_goals_block}

{media_block}
{attached_block}

{agency_block}

You have access to tools that let you: execute Python code, query the knowledge base, read the system database, check analytics, and update the Truth Bucket.

CRITICAL OPERATING RULES:
1. You are NOT a generic chatbot. You are an autonomous agency command interface.
2. When the user asks you to DO something that requires analysis, searching, or database reads — USE YOUR TOOLS. Do not answer from memory alone.
3. When the user mentions credentials, passwords, or authentication codes — USE the update_truth_bucket tool immediately.
4. When you reference an account or campaign, be specific about which one from the list above.
5. After tool results, synthesize a concise, expert final answer.
6. Never use markdown asterisks for bolding. Return plain text only.
7. Be direct, confident, and enterprise-grade in tone.
8. When the user says "use these images/videos" or "post these assets", refer to the AVAILABLE MEDIA ASSETS and CURRENTLY ATTACHED ASSETS sections above.
"""
    messages.insert(0, SystemMessage(content=system_prompt))

    mock_state = {
        "created_by": user_id,
        "goal_id": goal_id,
        "platforms": detected_platforms or [],
        "success_metrics": {}, "constraints": {},
        "asset_ids": asset_ids, "messages": [], "research_findings": {},
    }
    tools = get_agent_tools(mock_state)
    tool_map = {t.name: t for t in tools}
    llm = get_tool_llm(temperature=0.2).bind_tools(tools)

    max_loops = 6
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
                if chunk.content:
                    if isinstance(chunk.content, str):
                        accumulated_content += chunk.content
                    elif isinstance(chunk.content, list):
                        for part in chunk.content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                accumulated_content += part.get("text", "")

                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
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

        # ── Emit the model's textual reasoning ─────────────────────────────────
        if accumulated_content.strip():
            if tool_calls_buffer:
                yield {"type": "thinking", "content": accumulated_content.strip()}
            else:
                final_answer = accumulated_content
                for i in range(0, len(final_answer), 4):
                    yield {"type": "token", "content": final_answer[i:i+4]}
                    await asyncio.sleep(0.008)

        # ── Parse tool calls from buffer ──────────────────────────────────────
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

        ai_msg = AIMessage(
            content=accumulated_content,
            tool_calls=parsed_tool_calls if parsed_tool_calls else [],
        )
        messages.append(ai_msg)

        if not parsed_tool_calls:
            break

        # ── Execute each tool call ────────────────────────────────────────────
        tools_used = True
        for tc in parsed_tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool_id = tc["id"]

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

            tool_fn = tool_map.get(tool_name)
            if tool_fn:
                try:
                    result = await tool_fn.ainvoke(tool_args)
                    result_str = str(result)

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
