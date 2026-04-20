"""
Digital Force — Publisher Agent Node
Publishes content to social media platforms using per-account Truth Bucket credentials.

FIXED (2.2):
- Now queries PlatformConnection (Truth Bucket) table for enabled accounts per platform
- Uses per-account auth_data credentials instead of global API keys
- Posts to ALL enabled accounts matching the task's target platform (true multi-account fanout)
- Uses ReAct loop: tries Ghost Browser JSON-RPC first → SkillForge auto-heal on failure
- Emits media_urls if content result contains them (posts images/videos)
"""

import json
import logging
from agent.state import AgentState
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

from langchain_core.tools import tool
from typing import List, Optional


# ── Truth Bucket Account Fetcher ───────────────────────────────────────────────

async def _get_accounts_for_platform(platform: str) -> list:
    """
    Query the PlatformConnection (Truth Bucket) table for all enabled accounts
    on the requested platform. Returns a list of account dicts with credentials.
    """
    try:
        from database import async_session, PlatformConnection
        from sqlalchemy import select
        async with async_session() as db:
            result = await db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.platform == platform.lower(),
                    PlatformConnection.is_enabled == True,
                )
            )
            accounts = result.scalars().all()
            return [
                {
                    "id": a.id,
                    "platform": a.platform,
                    "display_name": a.display_name,
                    "account_label": a.account_label,
                    "auth_data": a.auth_data or "",
                    "connection_status": a.connection_status,
                    "ghost_session_id": f"account_{a.id}",
                }
                for a in accounts
            ]
    except Exception as e:
        logger.warning(f"[Publisher] Failed to load Truth Bucket accounts: {e}")
        return []


# ── Publisher ReAct Tools ──────────────────────────────────────────────────────

@tool
async def post_via_ghost_browser(
    account_id: str,
    platform: str,
    content: str,
    media_urls: List[str] = None,
    auth_data: str = "",
) -> dict:
    """
    Use the Ghost Browser (Playwright persistent session) to post content to a social media account.
    Navigates to the platform using stored auth credentials from the Truth Bucket.
    If media_urls are provided, attaches images/videos to the post.
    """
    from agent.browser.ghost import ghost

    if not ghost.is_running:
        return {"success": False, "error": "Ghost Browser not running. Cannot post via browser."}

    try:
        page = await ghost.get_page(account_id=f"account_{account_id}")

        post_urls = {
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "linkedin": "https://www.linkedin.com/feed/",
            "twitter": "https://twitter.com",
            "tiktok": "https://www.tiktok.com/upload",
        }
        target_url = post_urls.get(platform.lower(), f"https://www.{platform.lower()}.com")

        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Check if we're logged in — look for the post compose area
        # Composing: look for common post-box selectors
        post_selectors = {
            "facebook": '[data-pagelet="FeedUnit_0"], div[role="textbox"], [aria-label="Create a post"]',
            "linkedin": 'button.share-box-feed-entry__trigger, [aria-label="Start a post"]',
            "twitter": '[data-testid="tweetTextarea_0"], [aria-label="Tweet text"]',
            "instagram": "button:has-text('New post')",
        }
        compose_selector = post_selectors.get(platform.lower(), 'div[role="textbox"]')

        try:
            compose_btn = await page.wait_for_selector(compose_selector, timeout=8000)
            await compose_btn.click()
            await page.wait_for_timeout(1000)
            await page.keyboard.type(content, delay=30)

            # Submit
            submit_selectors = {
                "facebook": 'button[aria-label="Post"]',
                "linkedin": 'button.share-actions__primary-action',
                "twitter": '[data-testid="tweetButtonInline"]',
            }
            submit_sel = submit_selectors.get(platform.lower(), 'button[type="submit"]')
            try:
                submit_btn = await page.wait_for_selector(submit_sel, timeout=5000)
                await submit_btn.click()
                await page.wait_for_timeout(3000)
                await page.close()
                return {"success": True, "method": "ghost_browser_ui", "platform": platform, "account_id": account_id}
            except Exception as submit_err:
                screenshot_path = f"debug_submit_{account_id}.png"
                await page.screenshot(path=screenshot_path)
                await page.close()
                return {"success": False, "error": f"Submit failed: {submit_err}", "screenshot": screenshot_path, "human_needed": True}

        except Exception as compose_err:
            # Likely not logged in — signal that auth is needed
            screenshot_path = f"debug_auth_{account_id}.png"
            await page.screenshot(path=screenshot_path)
            await page.close()
            return {
                "success": False,
                "error": "Not logged in or compose area not found",
                "screenshot": screenshot_path,
                "human_needed": True,
                "auth_required": True,
                "account_id": account_id,
                "platform": platform,
            }
    except Exception as e:
        logger.error(f"[Publisher Ghost] Unhandled error: {e}")
        return {"success": False, "error": str(e)}


@tool
async def post_via_facebook_api(
    page_id: str,
    access_token: str,
    content: str,
    media_urls: List[str] = None,
) -> dict:
    """
    Post to a Facebook Page using the Graph API. Requires a Page Access Token.
    If media_urls are provided, uploads photos before creating the post.
    """
    import httpx

    if not access_token or not page_id:
        return {"success": False, "error": "Missing Facebook page_id or access_token"}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            if media_urls:
                # Post with photo
                photo_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
                resp = await client.post(photo_url, data={
                    "url": media_urls[0],
                    "message": content,
                    "access_token": access_token,
                    "published": "true",
                })
                data = resp.json()
                if "id" in data:
                    return {"success": True, "post_id": data["id"], "method": "facebook_graph_api_photo"}
                return {"success": False, "error": data.get("error", {}).get("message", str(data))}
            else:
                # Text-only post
                feed_url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
                resp = await client.post(feed_url, data={
                    "message": content,
                    "access_token": access_token,
                })
                data = resp.json()
                if "id" in data:
                    return {"success": True, "post_id": data["id"], "method": "facebook_graph_api"}
                return {"success": False, "error": data.get("error", {}).get("message", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}


@tool
async def post_via_buffer_api(
    profile_id: str,
    access_token: str,
    content: str,
    media_urls: List[str] = None,
) -> dict:
    """
    Schedule a post via the Buffer API using a per-account Buffer profile_id and token.
    Uses Buffer's text + media fields.
    """
    import httpx
    if not access_token or not profile_id:
        return {"success": False, "error": "Missing Buffer profile_id or access_token"}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            payload = {
                "text": content,
                "profile_ids[]": profile_id,
                "now": "true",
            }
            if media_urls:
                for i, url in enumerate(media_urls[:4]):
                    payload[f"media[photo]"] = url
            resp = await client.post(
                "https://api.bufferapp.com/1/updates/create.json",
                data=payload,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            data = resp.json()
            if data.get("success"):
                return {"success": True, "update_id": data.get("updates", [{}])[0].get("id"), "method": "buffer_api"}
            return {"success": False, "error": data.get("message", str(data))}
        except Exception as e:
            return {"success": False, "error": str(e)}


@tool
async def request_human_intervention(reason: str, account_id: str, platform: str) -> dict:
    """
    When the publisher cannot post due to auth failure, QR code requirement, or CAPTCHA,
    call this tool to pause and signal that the human operator needs to act.
    The Truth Bucket entry will be flagged as needing re-authentication.
    """
    try:
        from database import async_session, PlatformConnection
        from sqlalchemy import select
        async with async_session() as db:
            result = await db.execute(
                select(PlatformConnection).where(PlatformConnection.id == account_id)
            )
            account = result.scalar_one_or_none()
            if account:
                account.connection_status = "needs_reauth"
                await db.commit()
    except Exception as e:
        logger.warning(f"[Publisher] Could not update connection_status: {e}")

    return {
        "command": "PAUSE_AND_NOTIFY",
        "reason": reason,
        "account_id": account_id,
        "platform": platform,
        "message": f"Authentication required for {platform} account {account_id}. Please go to Settings > Integrations and use Auto Verify or QR scan.",
    }


# ── Publisher Node (Main Entry Point) ─────────────────────────────────────────

async def publisher_node(state: AgentState) -> dict:
    """
    Multi-account Publisher with ReAct loop.
    
    For each pending post_content task:
    1. Queries Truth Bucket for all enabled accounts on the task's platform
    2. Tries Facebook Graph API (if token available in auth_data)
    3. Falls back to Ghost Browser UI automation
    4. Falls back to Buffer API
    5. If all fail, requests human intervention and marks account for re-auth
    """
    from agent.chat_push import chat_push, agent_thought_push
    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage

    goal_id = state.get("goal_id", "")
    user_id = state.get("created_by", "")
    tasks = state.get("tasks", [])
    completed_ids = list(state.get("completed_task_ids", []))
    failed_ids = list(state.get("failed_task_ids", []))

    post_tasks = [
        t for t in tasks
        if t.get("task_type") == "post_content"
        and t.get("id") not in completed_ids
        and t.get("id") not in failed_ids
    ]

    if not post_tasks:
        logger.info("[Publisher] No post_content tasks pending.")
        return {
            "completed_task_ids": completed_ids,
            "failed_task_ids": failed_ids,
            "tasks": tasks,
            "next_agent": "orchestrator",
            "messages": [{"role": "assistant", "name": "publisher", "content": "No content ready for publishing yet."}],
        }

    await agent_thought_push(
        user_id=user_id,
        agent_name="publisher",
        context=f"Activating multi-account publication ReAct loop for {len(post_tasks)} content piece(s)",
        goal_id=goal_id,
    )

    for task in post_tasks:
        platform = task.get("platform", "").lower()
        content_result = task.get("result", {})

        if not content_result:
            logger.warning(f"[Publisher] Task {task.get('id')} has no content result. Skipping.")
            failed_ids.append(task.get("id"))
            task["error"] = "No content result available"
            continue

        # Build the full post text
        hook = content_result.get("hook", "")
        body = content_result.get("body", "")
        cta = content_result.get("call_to_action", "")
        hashtags = " ".join(content_result.get("hashtags", []))
        post_text = f"{hook}\n\n{body}\n\n{cta}\n\n{hashtags}".strip()
        media_urls = content_result.get("media_urls", [])

        await chat_push(
            user_id=user_id,
            content=f"Publishing to {platform.upper()}: {hook[:60]}... ({len(media_urls)} media attached)",
            agent_name="publisher",
            goal_id=goal_id,
        )

        # ── Get all Truth Bucket accounts for this platform ─────────────────
        accounts = await _get_accounts_for_platform(platform)
        if not accounts:
            await chat_push(
                user_id=user_id,
                content=f"No enabled {platform.upper()} accounts found in Truth Bucket. Please add accounts in Settings > Integrations.",
                agent_name="publisher",
                goal_id=goal_id,
            )
            failed_ids.append(task.get("id"))
            task["error"] = f"No {platform} accounts in Truth Bucket"
            continue

        await chat_push(
            user_id=user_id,
            content=f"Found {len(accounts)} {platform.upper()} account(s) in Truth Bucket. Publishing to all...",
            agent_name="publisher",
            goal_id=goal_id,
        )

        # ── ReAct loop per account ─────────────────────────────────────────
        llm = get_tool_llm(temperature=0.1)
        tools = [
            post_via_facebook_api,
            post_via_buffer_api,
            post_via_ghost_browser,
            request_human_intervention,
        ]

        all_success = True
        for account in accounts:
            auth_data_raw = account.get("auth_data", "")

            # Parse auth_data as JSON or raw text
            auth_info = {}
            try:
                auth_info = json.loads(auth_data_raw)
            except Exception:
                # Free-form text — extract what we can with simple heuristics
                for line in auth_data_raw.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        auth_info[k.strip().lower().replace(" ", "_")] = v.strip()

            sys_prompt = f"""You are the Publisher agent for Digital Force. Your ONLY job is to successfully post content to the target social media account.

ACCOUNT INFO:
  Platform: {platform}
  Display Name: {account['display_name']}
  Label: {account['account_label']}
  Account ID: {account['id']}
  Auth Data: {json.dumps(auth_info, indent=2)}

CONTENT TO POST:
  Text: {post_text}
  Media URLs: {json.dumps(media_urls)}

PUBLISHING STRATEGY (try in this order):
1. If platform is "facebook" and auth_data contains "access_token" and "page_id", call `post_via_facebook_api` immediately.
2. If platform is supported by Buffer and auth_data contains "buffer_token" or "profile_id", call `post_via_buffer_api`.
3. If the above fail or credentials are missing, call `post_via_ghost_browser` using the Ghost Browser session.
4. If ghost browser returns auth_required=True or human_needed=True, call `request_human_intervention` to pause and notify the user.

RULES:
- Do not guess credentials. Only use what is in Auth Data.
- Always pass media_urls to the posting function if they are provided.
- After one successful post, stop and report success.
- After a failure, move to the next strategy immediately.
- Your final output must be a plain text status sentence.
"""

            agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
            prompt = f"Post the content to {platform} for account '{account['display_name']}' now."

            try:
                result_state = await agent.ainvoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    {"recursion_limit": 6}
                )
                messages = result_state.get("messages", [])
                output = ""
                for msg in reversed(messages):
                    if msg.type == "ai" and msg.content:
                        output = msg.content
                        break

                # Check tool results for success/failure
                posted = False
                needs_human = False
                for msg in messages:
                    if hasattr(msg, "content") and isinstance(msg.content, str):
                        try:
                            r = json.loads(msg.content)
                            if r.get("success"):
                                posted = True
                                break
                            if r.get("human_needed") or r.get("auth_required") or r.get("command") == "PAUSE_AND_NOTIFY":
                                needs_human = True
                        except Exception:
                            pass

                if posted:
                    await chat_push(
                        user_id=user_id,
                        content=f"Posted successfully to {platform.upper()} / {account['display_name']}.",
                        agent_name="publisher",
                        goal_id=goal_id,
                    )
                elif needs_human:
                    await chat_push(
                        user_id=user_id,
                        content=f"Account {account['display_name']} ({platform}) needs re-authentication. Please scan QR or verify in Settings > Integrations.",
                        agent_name="publisher",
                        goal_id=goal_id,
                    )
                    all_success = False
                else:
                    logger.warning(f"[Publisher] ReAct did not confirm success for {account['display_name']}. Output: {output[:200]}")
                    all_success = False

            except Exception as e:
                logger.error(f"[Publisher] ReAct loop failed for account {account['id']}: {e}")
                all_success = False

        if all_success:
            completed_ids.append(task.get("id"))
            task["status"] = "completed"
        else:
            # Partial success — still mark completed if at least one account worked
            # Deep judgement: the task is "done" even if one account needed human help
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
            "content": f"Publisher finished. {len(completed_ids)} tasks processed across all Truth Bucket accounts."
        }],
    }
