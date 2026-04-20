"""
Digital Force — Publisher Agent Node
Posts content to all platforms via Buffer API + Facebook Graph API.
"""

import json
import logging
import httpx
from datetime import datetime
from agent.state import AgentState
from agent.chat_push import chat_push, agent_thought_push
from config import get_settings
from agent.tools.whatsapp_web import send_whatsapp_message

logger = logging.getLogger(__name__)
settings = get_settings()

BUFFER_API = "https://api.bufferapp.com/1"
FB_API = f"https://graph.facebook.com/{settings.facebook_api_version}"

# Platform → Buffer profile lookup (set via Settings in DB)
BUFFER_PLATFORMS = {"linkedin", "twitter", "tiktok", "instagram", "youtube", "pinterest", "threads"}
FACEBOOK_PLATFORMS = {"facebook"}


# ─── Buffer Publisher ─────────────────────────────────────

async def _get_buffer_profiles() -> dict:
    """Get all connected Buffer profile IDs keyed by service."""
    if not settings.buffer_access_token:
        return {}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BUFFER_API}/profiles.json",
            params={"access_token": settings.buffer_access_token}
        )
        if resp.status_code == 200:
            profiles = resp.json()
            return {p["service"]: p["id"] for p in profiles if p.get("id")}
    return {}


async def _buffer_post(
    profile_id: str,
    text: str,
    media_urls: list[str] = None,
    scheduled_at: str = None,
) -> dict:
    """Post to a Buffer profile."""
    payload = {
        "access_token": settings.buffer_access_token,
        "profile_ids[]": profile_id,
        "text": text,
        "now": scheduled_at is None,
    }
    if scheduled_at:
        payload["scheduled_at"] = scheduled_at
    if media_urls:
        for i, url in enumerate(media_urls[:4]):
            payload[f"media[picture]"] = url  # Buffer supports single image this way

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BUFFER_API}/updates/create.json", data=payload)
        data = resp.json()
        if resp.status_code in (200, 201) and data.get("success"):
            updates = data.get("updates", [{}])
            return {"success": True, "platform_post_id": updates[0].get("id"), "platform_url": None}
        return {"success": False, "error": data.get("message", "Buffer API error")}


# ─── Facebook Graph Publisher ──────────────────────────────

async def _facebook_post(
    text: str,
    media_urls: list[str] = None,
    scheduled_at: str = None,
) -> dict:
    """Post to Facebook Page via Graph API."""
    if not settings.facebook_access_token or not settings.facebook_page_id:
        return {"success": False, "error": "Facebook not configured"}

    page_id = settings.facebook_page_id
    token = settings.facebook_access_token

    async with httpx.AsyncClient() as client:
        if media_urls:
            # Photo post
            endpoint = f"{FB_API}/{page_id}/photos"
            payload = {"message": text, "url": media_urls[0], "access_token": token}
        else:
            # Text/link post
            endpoint = f"{FB_API}/{page_id}/feed"
            payload = {"message": text, "access_token": token}

        if scheduled_at:
            from datetime import datetime
            dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            payload["published"] = "false"
            payload["scheduled_publish_time"] = int(dt.timestamp())

        resp = await client.post(endpoint, data=payload)
        data = resp.json()

        if "id" in data:
            post_id = data["id"]
            return {
                "success": True,
                "platform_post_id": post_id,
                "platform_url": f"https://facebook.com/{post_id}"
            }
        return {"success": False, "error": data.get("error", {}).get("message", "Facebook API error")}


# ─── Publisher ReAct Tools ─────────────────────────────────────────
from langchain_core.tools import tool

@tool
async def post_via_buffer(platform: str, text: str, media_urls: list[str] = None) -> dict:
    """Post to Buffer. Only works for linkedin, twitter, tiktok, instagram, youtube, pinterest, threads."""
    buffer_profiles = await _get_buffer_profiles()
    profile_id = buffer_profiles.get(platform.lower())
    if not profile_id:
        return {"success": False, "error": f"No Buffer profile linked for {platform}."}
    return await _buffer_post(profile_id, text, media_urls)

@tool
async def post_via_facebook_api(text: str, media_urls: list[str] = None) -> dict:
    """Post to Facebook Page natively using Graph API."""
    return await _facebook_post(text, media_urls)

@tool
async def post_via_whatsapp_web(target_phone: str, text: str) -> dict:
    """Post directly to WhatsApp using Baileys."""
    phone = "".join(filter(str.isdigit, target_phone))
    if not phone:
        return {"success": False, "error": "WhatsApp requires a phone number."}
    resp = await send_whatsapp_message(phone, text)
    if resp.get("status") == "ok":
        return {"success": True, "platform_post_id": "whatsapp_ghost"}
    elif resp.get("status") == "auth_required":
        return {"success": False, "error": resp.get("error")}
    return {"success": False, "error": resp.get("error", "WhatsApp failed")}

@tool
async def use_forged_skill(platform: str, text: str, media_urls: list[str] = None) -> dict:
    """Run a custom Python skill previously forged by SkillForge. Use this if API options fail."""
    from agent.skills.registry import skills_for_task, run_skill
    candidates = skills_for_task(f"post to {platform} social media")
    for skill_name in candidates[:2]:
        try:
            res = await run_skill(skill_name, text=text, platform=platform, media_urls=media_urls)
            if res.get("success"):
                return res
        except Exception as e:
            logger.error(f"Generated skill {skill_name} failed: {e}")
    return {"success": False, "error": f"No working forged skills found for {platform}."}

@tool
async def escalate_to_skillforge(platform: str, account_label: str) -> dict:
    """If all APIs and Skills fail, call this tool to trigger an autonomous Sandbox Playwright routing. This WILL FAIL the current task but allow SkillForge to auto-heal it."""
    return {
        "success": False, 
        "error": f"API publishing unavailable. FATAL. Require SkillForge to deploy Playwright Ghost Browser for {account_label} fallback."
    }

# ─── Main Publisher Node ───────────────────────────────────

async def publisher_node(state: AgentState) -> dict:
    """
    Takes ONE approved task marked as 'post_content', resolves content + assets,
    and publishes to the appropriate platform using a ReAct execution loop.
    """
    goal_id = state['goal_id']
    user_id = state.get('created_by', '')
    logger.info(f"[Publisher] Booting ReAct Publisher sequence for {goal_id}")

    tasks = state.get("tasks", [])
    completed = set(state.get("completed_task_ids", []))
    failed = set(state.get("failed_task_ids", []))

    pending_task = next(
        (t for t in tasks if t.get("task_type") == "post_content" and t.get("id") not in completed | failed),
        None
    )

    if not pending_task:
        return {
            "next_agent": "monitor",
            "messages": [{"role": "assistant", "name": "publisher", "content": "No pending publish tasks."}]
        }

    await agent_thought_push(
        user_id=user_id,
        context=f"initiating the network publishing sequence via ReAct routing",
        agent_name="publisher",
        goal_id=goal_id,
    )

    platform = pending_task.get("platform", "").lower()
    content = pending_task.get("result", {})
    caption = content.get("caption", pending_task.get("description", ""))
    hashtags = " ".join([f"#{h.lstrip('#')}" for h in content.get("hashtags", [])])
    full_text = f"{caption}\n\n{hashtags}".strip()
    media_urls = content.get("media_urls", [])
    account_label = pending_task.get("account_label", "Unknown")

    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    import json
    
    llm = get_tool_llm(temperature=0.0)
    tools = [post_via_buffer, post_via_facebook_api, post_via_whatsapp_web, use_forged_skill, escalate_to_skillforge]
    
    sys_prompt = f"""You are the Network Publisher. Your job is to post social media content to {platform}.
You have 5 physical tools at your disposal representing direct pathways to the internet.
You MUST try the fast API methods first (Buffer/Facebook/WhatsApp). If they fail or return errors, you MUST try `use_forged_skill`. 
If absolutely everything fails, call `escalate_to_skillforge` to crash the task and trigger the auto-healer.

Once a post succeeds (success: True), STOP USING TOOLS and output exactly:
SUCCESS: <tool_name_used>

If it fails completely after escalation, output exactly:
FAILED: <reason>
"""

    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
    
    prompt = f"""
PLATFORM: {platform}
ACCOUNT_LABEL: {account_label}
TEXT: {full_text}
MEDIA_URLS: {media_urls}
"""

    try:
        final_state = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]}, {"recursion_limit": 6})
    except Exception as e:
        logger.error(f"[Publisher ReAct Engine] Crashed: {e}")
        return {"error": str(e), "next_agent": "monitor"}

    messages = final_state.get("messages", [])
    output = ""
    for msg in reversed(messages):
        if msg.type == "ai" and msg.content:
            output = msg.content
            break

    # Resolve success based on the ReAct trajectory
    success = "SUCCESS" in output
    result_dict = {"success": success, "error": output if not success else None}

    # If it hit the Auth Barrier or Escalate barrier, fetch auth data for SkillForge
    if not success:
        from database import async_session, PlatformConnection
        from sqlalchemy import select
        auth_data = ""
        connection_id = pending_task.get("connection_id")
        try:
            async with async_session() as session:
                if connection_id:
                    stmt = select(PlatformConnection).where(PlatformConnection.id == connection_id)
                    conn = (await session.execute(stmt)).scalar_one_or_none()
                    if conn:
                        auth_data = conn.auth_data or ""
        except Exception:
            pass
        
        result_dict["auth_data"] = auth_data
        result_dict["connection_id"] = connection_id
        result_dict["error"] = f"API unavailable or failed. Auth Data bound. Reason: {output}"

    newly_completed = []
    newly_failed = []
    log_messages = []

    if success:
        newly_completed.append(pending_task.get("id"))
        await agent_thought_push(
            user_id=user_id,
            context=f"successfully routed and published payload to {platform} via ReAct",
            agent_name="publisher",
            goal_id=goal_id,
            metadata={"platform": platform},
        )
        log_messages.append({"role": "assistant", "name": "publisher", "content": f"✅ Posted to {platform}: {caption[:50]}..."})
    else:
        newly_failed.append(pending_task.get("id"))
        pending_task["error"] = result_dict.get('error', 'Unknown error')
        if "auth_data" in result_dict:
            pending_task["auth_data"] = result_dict["auth_data"]
            pending_task["connection_id"] = result_dict["connection_id"]
        
        # Determine if WhatsApp QR hit
        if "auth_required" in output or "WhatsApp" in output:
             await chat_push(user_id, f"🚨 **WhatsApp Auth Required!**\nCheck backend logs for QR.", "publisher", goal_id)
            
        await agent_thought_push(
            user_id=user_id,
            context=f"encountered transmission failure on {platform}, escalated to auto-healer.",
            agent_name="publisher",
            goal_id=goal_id,
        )
        log_messages.append({"role": "assistant", "name": "publisher", "content": f"❌ Failed {platform}. Escalated to auto-healer."})

    return {
        "tasks": tasks,  
        "completed_task_ids": newly_completed,
        "failed_task_ids": newly_failed, 
        "messages": log_messages,
        "next_agent": "skillforge" if newly_failed else "monitor",
        "current_task_id": None # Reset for next cycle
    }
