"""
Digital Force — Publisher Agent Node
=====================================
Posts content to social media using the best available method per platform.

STRATEGY:
  Facebook  → Facebook Graph API (primary) → Ghost Browser (fallback)
  All Other → Ghost Browser vision agent (LinkedIn, Instagram, TikTok,
              Twitter, YouTube, WhatsApp, Pinterest — anything with a browser)

The Ghost Browser approach requires NO API, NO OAuth approval, NO SDK.
The agent literally browses to the platform, reads the screen with vision,
finds the compose area, types the content, attaches media, and submits.
It works on any platform a human can use.

Truth Bucket provides per-account credentials (username/password or cookies)
that the Ghost Browser uses to maintain authenticated sessions.
"""

import json
import logging
from typing import List, Optional
from agent.state import AgentState
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Truth Bucket lookup ────────────────────────────────────────────────────────

async def _get_accounts_for_platform(platform: str) -> list:
    """Load all enabled accounts for a platform from the Truth Bucket."""
    try:
        from database import async_session, PlatformConnection
        from sqlalchemy import select
        async with async_session() as db:
            res = await db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.platform == platform.lower(),
                    PlatformConnection.is_enabled == True,
                )
            )
            accounts = res.scalars().all()
            return [
                {
                    "id": a.id,
                    "platform": a.platform,
                    "display_name": a.display_name,
                    "account_label": a.account_label,
                    "auth_data": a.auth_data or "",
                    "web_username": a.web_username or "",
                    "connection_status": a.connection_status,
                }
                for a in accounts
            ]
    except Exception as e:
        logger.warning(f"[Publisher] Truth Bucket lookup failed: {e}")
        return []


async def _mark_account_needs_reauth(account_id: str):
    """Flag an account in the Truth Bucket as needing re-authentication."""
    try:
        from database import async_session, PlatformConnection
        async with async_session() as db:
            account = await db.get(PlatformConnection, account_id)
            if account:
                account.connection_status = "needs_reauth"
                await db.commit()
    except Exception as e:
        logger.warning(f"[Publisher] Could not update account status: {e}")


# ── Facebook Graph API Publisher ──────────────────────────────────────────────

async def _post_facebook_api(
    page_id: str,
    access_token: str,
    content: str,
    media_urls: List[str],
) -> dict:
    """
    Post to a Facebook Page using the Graph API.
    Supports text-only posts and photo posts (links a hosted image URL).
    """
    import httpx
    api_version = settings.facebook_api_version or "v21.0"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            if media_urls:
                # Photo post with caption
                resp = await client.post(
                    f"https://graph.facebook.com/{api_version}/{page_id}/photos",
                    data={
                        "url": media_urls[0],  # First image
                        "message": content,
                        "access_token": access_token,
                        "published": "true",
                    },
                )
                data = resp.json()
                if "id" in data:
                    return {"success": True, "post_id": data["id"], "method": "facebook_graph_api_photo"}
                return {"success": False, "error": data.get("error", {}).get("message", str(data))}
            else:
                # Text post
                resp = await client.post(
                    f"https://graph.facebook.com/{api_version}/{page_id}/feed",
                    data={"message": content, "access_token": access_token},
                )
                data = resp.json()
                if "id" in data:
                    return {"success": True, "post_id": data["id"], "method": "facebook_graph_api"}
                return {"success": False, "error": data.get("error", {}).get("message", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ── Universal Ghost Browser Publisher ─────────────────────────────────────────

async def _post_via_ghost_browser(
    account: dict,
    platform: str,
    content: str,
    media_urls: List[str],
    user_id: str,
    goal_id: str,
) -> dict:
    """
    Universal vision-driven Ghost Browser publisher.

    The agent:
    1. Navigates to the platform homepage
    2. Uses vision (ghost_see) to check login state
    3. If not logged in, attempts login using Truth Bucket credentials
    4. Finds the compose / create post area using vision
    5. Types the content naturally (human-speed keystrokes)
    6. Uploads any media files if available
    7. Submits and confirms via vision

    Works for: LinkedIn, Instagram, Twitter/X, TikTok, Pinterest, YouTube
    community posts, Reddit, Facebook (fallback), and any future platform.
    """
    from agent.llm import get_tool_llm
    from agent.chat_push import chat_push, agent_thought_push
    from agent.browser.react_browser import (
        ghost_goto, ghost_see, ghost_click, ghost_type,
        ghost_press_key, ghost_upload_file, ghost_wait_for,
        ghost_scroll, ghost_get_page_text,
    )
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage

    account_id = account["id"]
    auth_data_raw = account.get("auth_data", "")
    web_username = account.get("web_username", "")

    # Parse auth_data — may be JSON or free-form key: value
    auth_info = {}
    try:
        auth_info = json.loads(auth_data_raw)
    except Exception:
        for line in auth_data_raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                auth_info[k.strip().lower().replace(" ", "_")] = v.strip()

    # Download media to local temp files so we can upload them
    local_media_paths = []
    if media_urls:
        import httpx, tempfile, os
        for url in media_urls[:4]:  # Limit to 4 media items
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(url)
                    ext = url.split(".")[-1].split("?")[0][:4] or "jpg"
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
                    tmp.write(r.content)
                    tmp.close()
                    local_media_paths.append(tmp.name)
            except Exception as e:
                logger.warning(f"[Publisher] Could not download media {url}: {e}")

    # Build system prompt for the Ghost Browser ReAct agent
    platform_hint = {
        "linkedin":  "https://linkedin.com/feed/",
        "instagram": "https://www.instagram.com/",
        "twitter":   "https://twitter.com/home",
        "tiktok":    "https://www.tiktok.com/upload",
        "pinterest": "https://www.pinterest.com/",
        "facebook":  "https://www.facebook.com/",
        "youtube":   "https://studio.youtube.com/",
    }.get(platform.lower(), f"https://www.{platform.lower()}.com/")

    media_instruction = (
        f"After typing the content, upload these local files: {local_media_paths}"
        if local_media_paths
        else "This is a text-only post, no media to upload."
    )

    sys_prompt = f"""You are a Ghost Browser operator for Digital Force. You control a real Chromium browser remotely.
Your mission: Post content to {platform.upper()} for the account '{account['display_name']}'.

ACCOUNT CREDENTIALS (from Truth Bucket):
{json.dumps(auth_info, indent=2)}
Username/Email: {web_username or auth_info.get('email', auth_info.get('username', 'not set'))}

CONTENT TO POST:
{content}

MEDIA: {media_instruction}

OPERATING PROCEDURE — follow this sequence:
1. Call ghost_goto to navigate to {platform_hint} (account_id='{account_id}')
2. Call ghost_see to check: "Am I logged into {platform}? Is there a post compose area visible?"
3. IF NOT LOGGED IN:
   - Navigate to the login page
   - Click the email/username field, use ghost_type to enter the username
   - Click the password field, use ghost_type to enter the password
   - Click login/sign-in button
   - Wait for the feed/home page to load
   - Call ghost_see to confirm login succeeded
4. FIND THE COMPOSE / CREATE POST AREA:
   - Look for: "Start a post", "What's on your mind?", "Create", "+ New", "Compose"
   - Call ghost_click to open it
5. TYPE THE CONTENT:
   - Call ghost_click on the text area to focus it
   - Call ghost_type with the full post content
6. IF MEDIA: Call ghost_upload_file for each local media path
7. SUBMIT:
   - Find the "Post", "Share", "Tweet", "Publish" button
   - Call ghost_click to submit
8. CONFIRM:
   - Call ghost_wait_for "confirmation that post was published successfully, or any error message"
   - Report what you saw

RULES:
- Always pass account_id='{account_id}' to every tool call
- If you hit a CAPTCHA or phone verification, call ghost_see to take a screenshot and report it
- Never skip steps — always verify with ghost_see before clicking
- Do not use markdown asterisks in your final report
"""

    tools = [
        ghost_goto, ghost_see, ghost_click, ghost_type,
        ghost_press_key, ghost_upload_file, ghost_wait_for,
        ghost_scroll, ghost_get_page_text,
    ]

    llm = get_tool_llm(temperature=0.1)
    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))

    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=f"Post to {platform} for account {account['display_name']} now.")]},
            {"recursion_limit": 20},  # Give the agent room to navigate + login + post
        )
        messages = result.get("messages", [])
        output = ""
        for msg in reversed(messages):
            if msg.type == "ai" and msg.content:
                output = msg.content
                break

        # Clean up temp files
        for path in local_media_paths:
            try:
                import os
                os.unlink(path)
            except Exception:
                pass

        # Determine success from final output
        success_keywords = ["success", "posted", "published", "shared", "submitted", "live"]
        failure_keywords = ["captcha", "verification", "phone", "error", "failed", "blocked", "login"]

        output_lower = output.lower()
        if any(k in output_lower for k in success_keywords) and not any(k in output_lower for k in failure_keywords):
            return {"success": True, "method": "ghost_browser_vision", "output": output}
        elif "captcha" in output_lower or "verification" in output_lower or "phone" in output_lower:
            return {"success": False, "error": "Human verification required", "human_needed": True, "output": output}
        else:
            return {"success": False, "error": output[:200], "output": output}

    except Exception as e:
        logger.error(f"[Publisher Ghost] ReAct loop error: {e}", exc_info=True)
        # Clean up temp files on error too
        for path in local_media_paths:
            try:
                import os
                os.unlink(path)
            except Exception:
                pass
        return {"success": False, "error": str(e)}


# ── Main Publisher Node ────────────────────────────────────────────────────────

async def publisher_node(state: AgentState) -> dict:
    """
    Multi-account, multi-platform publisher.

    For each pending post_content task:
      1. Look up all enabled accounts for the task's platform in the Truth Bucket
      2. For Facebook: try Graph API, fall back to Ghost Browser on failure
      3. For everything else: Ghost Browser vision agent directly
      4. Push live status updates to chat as each account is posted to
    """
    from agent.chat_push import chat_push, agent_thought_push

    goal_id = state.get("goal_id", "")
    user_id = state.get("created_by", "")
    tasks = state.get("tasks", [])
    completed_ids = list(state.get("completed_task_ids", []))
    failed_ids = list(state.get("failed_task_ids", []))

    # Find all tasks that have content ready to publish
    post_tasks = [
        t for t in tasks
        if t.get("task_type") == "post_content"
        and t.get("id") not in completed_ids
        and t.get("id") not in failed_ids
    ]

    if not post_tasks:
        return {
            "completed_task_ids": completed_ids,
            "failed_task_ids": failed_ids,
            "tasks": tasks,
            "next_agent": "orchestrator",
            "messages": [{"role": "assistant", "name": "publisher", "content": "No publishable content tasks pending."}],
        }

    await agent_thought_push(
        user_id=user_id,
        agent_name="publisher",
        context=f"Activating publishing loop for {len(post_tasks)} content piece(s) across all Truth Bucket accounts",
        goal_id=goal_id,
    )

    for task in post_tasks:
        platform = task.get("platform", "").lower()
        content_result = task.get("result", {})

        if not content_result:
            failed_ids.append(task.get("id"))
            task["error"] = "No content result — ContentDirector did not produce output"
            continue

        # Build the full post text from content director output
        hook = content_result.get("hook", "")
        body = content_result.get("body", "")
        cta = content_result.get("call_to_action", "")
        hashtags = " ".join(content_result.get("hashtags", []))
        post_text = "\n\n".join(filter(None, [hook, body, cta, hashtags])).strip()
        media_urls: List[str] = content_result.get("media_urls", [])

        await chat_push(
            user_id=user_id,
            content=f"Publishing to {platform.upper()}: \"{hook[:70]}...\" ({len(media_urls)} media file(s))",
            agent_name="publisher",
            goal_id=goal_id,
        )

        # Load all matching accounts from Truth Bucket
        accounts = await _get_accounts_for_platform(platform)

        if not accounts:
            await chat_push(
                user_id=user_id,
                content=f"No enabled {platform.upper()} accounts found in Truth Bucket. Add accounts in Settings > Integrations.",
                agent_name="publisher",
                goal_id=goal_id,
            )
            failed_ids.append(task.get("id"))
            task["error"] = f"No {platform} accounts configured"
            continue

        await chat_push(
            user_id=user_id,
            content=f"Found {len(accounts)} {platform.upper()} account(s). Publishing to all now...",
            agent_name="publisher",
            goal_id=goal_id,
        )

        task_success = True

        for account in accounts:
            auth_data_raw = account.get("auth_data", "")
            auth_info = {}
            try:
                auth_info = json.loads(auth_data_raw)
            except Exception:
                for line in auth_data_raw.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        auth_info[k.strip().lower().replace(" ", "_")] = v.strip()

            post_result = None

            # ── FACEBOOK: Graph API first, Ghost Browser fallback ──────────────
            if platform == "facebook":
                page_id = auth_info.get("page_id") or settings.facebook_page_id
                access_token = auth_info.get("access_token") or settings.facebook_access_token

                if page_id and access_token:
                    await agent_thought_push(
                        user_id=user_id,
                        agent_name="publisher",
                        context=f"Attempting Facebook Graph API for {account['display_name']}",
                        goal_id=goal_id,
                    )
                    post_result = await _post_facebook_api(page_id, access_token, post_text, media_urls)

                    if post_result.get("success"):
                        await chat_push(
                            user_id=user_id,
                            content=f"Posted to Facebook page '{account['display_name']}' via Graph API. Post ID: {post_result.get('post_id')}",
                            agent_name="publisher",
                            goal_id=goal_id,
                        )
                        continue  # Move to next account

                    # API failed — fall through to Ghost Browser
                    logger.warning(f"[Publisher] Facebook API failed for {account['display_name']}: {post_result.get('error')}. Falling back to Ghost Browser.")
                    await agent_thought_push(
                        user_id=user_id,
                        agent_name="publisher",
                        context=f"Facebook Graph API failed ({post_result.get('error', 'unknown')}). Switching to Ghost Browser physical posting.",
                        goal_id=goal_id,
                    )

            # ── ALL PLATFORMS (including FB fallback): Ghost Browser vision agent
            await agent_thought_push(
                user_id=user_id,
                agent_name="publisher",
                context=f"Ghost Browser agent opening {platform} for account '{account['display_name']}' — navigating and posting physically",
                goal_id=goal_id,
            )

            post_result = await _post_via_ghost_browser(
                account=account,
                platform=platform,
                content=post_text,
                media_urls=media_urls,
                user_id=user_id,
                goal_id=goal_id,
            )

            if post_result.get("success"):
                await chat_push(
                    user_id=user_id,
                    content=f"Posted to {platform.upper()} / {account['display_name']} via Ghost Browser.",
                    agent_name="publisher",
                    goal_id=goal_id,
                )
            elif post_result.get("human_needed"):
                await chat_push(
                    user_id=user_id,
                    content=f"Account '{account['display_name']}' ({platform}) hit a verification wall (CAPTCHA or phone check). Please log in manually via Settings > Integrations, then re-run the campaign.",
                    agent_name="publisher",
                    goal_id=goal_id,
                )
                await _mark_account_needs_reauth(account["id"])
                task_success = False
            else:
                await chat_push(
                    user_id=user_id,
                    content=f"Ghost Browser could not post to {account['display_name']} ({platform}). Reason: {post_result.get('error', 'Unknown')}",
                    agent_name="publisher",
                    goal_id=goal_id,
                )
                task_success = False

        # Mark task based on overall account success
        if task_success:
            completed_ids.append(task.get("id"))
            task["status"] = "completed"
        else:
            # Partial — at least we attempted. Mark completed so the loop moves forward.
            completed_ids.append(task.get("id"))
            task["status"] = "completed_partial"

    return {
        "completed_task_ids": completed_ids,
        "failed_task_ids": failed_ids,
        "tasks": tasks,
        "next_agent": "orchestrator",
        "messages": [{
            "role": "assistant",
            "name": "publisher",
            "content": f"Publisher finished. Processed {len(post_tasks)} task(s) across all Truth Bucket accounts.",
        }],
    }
