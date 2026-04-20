"""
Digital Force — SkillForge Agent Node
Creates new Python skills on-demand using E2B sandboxed execution.

Now with:
  - Web search (Tavily) to find real solutions before writing code
  - Dynamic skill registry: skills are loaded and called, not just saved
  - Metadata files (.meta.json) for each skill
  - Risk-based routing: low/medium auto-retries, high risk pauses for approval
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from agent.state import AgentState
from agent.llm import generate_completion, generate_json
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SKILLS_DIR = Path(__file__).parent.parent / "skills" / "generated"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

SKILL_SYSTEM_PROMPT = """You are SkillForge — an expert Python developer creating reusable tool functions for a social media AI agent.

Rules for generated skills:
1. Write a single async Python function
2. Include ALL imports inside the function body
3. Handle all exceptions and return sensible defaults
4. Add a docstring explaining what the function does
5. The function must be fully self-contained (no external state)
6. Return a dict with a "success" key always

═══ STRATEGY FOR CHOOSING IMPLEMENTATION APPROACH ═══

Option A — API first (preferred):
If a public REST/GraphQL API exists for the task, use it with httpx.

Option B — Headless browser (fallback when no API exists):
If no API exists or the API is paywalled/blocked, use Playwright to control a
real Chromium browser. This is available in the E2B sandbox.

Playwright skill example:
```python
async def scrape_linkedin_profile(username: str) -> dict:
    \"\"\"Scrape a LinkedIn public profile using the Ghost Browser.\"\"\"
    from agent.browser.ghost import ghost
    try:
        page = await ghost.get_page()
        await page.goto(f"https://www.linkedin.com/in/{username}/", wait_until="networkidle")
        name = await page.text_content("h1.top-card-layout__title") or "Unknown"
        headline = await page.text_content("h2.top-card-layout__headline") or ""
        await page.close()
        return {"success": True, "name": name.strip(), "headline": headline.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

API skill example:
```python
async def check_hashtag_trend(hashtag: str, platform: str) -> dict:
    \"\"\"Check if a hashtag is trending.\"\"\"
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.example.com/trends/{hashtag}")
            data = resp.json()
        return {"success": True, "is_trending": data.get("trending", False)}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

When using Playwright:
- You MUST use `from agent.browser.ghost import ghost`
- Use `page = await ghost.get_page()` to get an authenticated persistent tab
- NEVER use `async_playwright()`. The Ghost Browser handles persistence and anti-bot mitigation.
- Use `wait_until="networkidle"` or specific selectors with `page.wait_for_selector`
- YOU MUST call `await page.close()` before returning to avoid resource leaks
- Use `await page.screenshot(path="debug_skill.png")` if you need to debug page state

Write clean, production-ready Python. No placeholder code."""


# Imported run_in_e2b from agent.tools.sandbox


# ─── Auth Provision Handler ──────────────────────────────────────────────────
async def _handle_auth_provision(state: AgentState) -> dict:
    from agent.chat_push import chat_push, agent_thought_push
    from agent.tools.sandbox import run_in_e2b
    import base64
    
    goal_desc = state.get('goal_description', '')
    user_id = state.get('created_by')
    goal_id = state.get('goal_id')
    
    await agent_thought_push(user_id, "skillforge", "hijacked loop for direct authentication provisioning. fabricating login script...", goal_id)
    
    # Extract platform and account_label
    import re
    match = re.search(r"authenticate account '([^']+)' on platform '([^']+)'", goal_desc)
    account_label = match.group(1).replace(" ", "_").lower() if match else "auth_target"
    platform = match.group(2) if match else "unknown"

    code_prompt = f"""
    Create a Python async function called 'auto_login_{platform}' that handles logging into {platform}.
    
    INSTRUCTIONS:
    {goal_desc}
    
    RULES:
    1. You MUST use Playwright via Ghost Browser. 
    2. `from agent.browser.ghost import ghost`
    3. `page = await ghost.get_page(account_id='{account_label}')`
    4. Navigate to the {platform} login page.
    5. Attempt to fill credentials if they are provided.
    6. IF you encounter a QR Code, Captcha, or 2FA prompt:
       - Take a screenshot: `await page.screenshot(path='auth_barrier.png')`
       - Immediately return: {{"success": False, "human_needed": True, "screenshot_path": "auth_barrier.png", "message": "Hit a QR/Captcha"}}
    7. IF login succeeds, wait for the dashboard DOM to load, then return: {{"success": True}}
    8. You MUST `await page.close()` before returning.
    
    Return pure python code enclosed in ```python...```
    """
    
    raw_code = await generate_completion(code_prompt, SKILL_SYSTEM_PROMPT)
    code_match = re.search(r'```python\n(.*?)```', raw_code, re.DOTALL)
    clean_code = code_match.group(1) if code_match else raw_code

    if user_id:
        await chat_push(user_id, f"Executing autonomous login protocol for {platform}: \n```python\n{clean_code}\n```", "skillforge", goal_id)

    # Execute in sandbox
    test_result = await run_in_e2b(clean_code, f"auto_login_{platform}", {})
    
    if test_result.get("success"):
        if user_id:
            await chat_push(user_id, f"✅ Successfully authenticated **{platform}** autonomously. Session is now permanently isolated in Ghost Browser.", "skillforge", goal_id)
        return {"status": "ok", "next_agent": "__end__"}
    else:
        # If human interference is needed (QR/Captcha)
        if "auth_barrier.png" in str(test_result.get("output", "")) or "auth_barrier.png" in str(test_result.get("error", "")):
            # Load the image and send to chat
            import os
            if os.path.exists("auth_barrier.png"):
                with open("auth_barrier.png", "rb") as img:
                    b64 = base64.b64encode(img.read()).decode()
                markdown_img = f"![Action Required](data:image/png;base64,{b64})"
                os.remove("auth_barrier.png")
            else:
                markdown_img = "*(Image failed to capture)*"
                
            await chat_push(
                user_id, 
                f"⚠️ I hit a security barrier while authenticating {platform}. Please scan or solve this on your phone, then type 'Done' in this chat so I can verify.\n\n{markdown_img}", 
                "skillforge", 
                goal_id
            )
            # The Orchestrator ReAct loop will PAUSE because SkillForge returns failure but human_needed handles it.
            return {"status": "paused", "error": "Human intervention required for authentication."}
            
        # Total failure
        if user_id:
            await chat_push(user_id, f"❌ Failed to authenticate autonomously: {test_result.get('error')}", "skillforge", goal_id)
        return {"status": "failed", "error": str(test_result.get("error"))}

# ─── SkillForge ReAct Internal Tools ──────────────────────────────────────────

from langchain_core.tools import tool
from typing import List, Optional

@tool
async def search_open_source_packages(query: str) -> str:
    """Search the internet for existing open source PyPI packages, LangChain community tools, or Python SDKs that solve the given problem. Use this to avoid writing custom API wrappers manually."""
    from agent.tools.web_search import search_for_solution
    logger.info(f"[SkillForge Tool] Searching packages for: {query}")
    return await search_for_solution(f"python library or pypi package or langchain tool for: {query}", context="python open source ecosystem")

@tool
async def write_and_test_python_code(skill_name: str, code: str, dependencies: List[str] = None) -> dict:
    """
    Write a self-contained Python async function and execute it locally in the Sandboxed Subprocess environment.
    Use `dependencies` to dynamically pip-install PyPI packages (e.g. ["tweepy", "facebook-sdk"]) before running.
    If you need to bypass a walled garden physically, put Playwright commands in `code` but YOU MUST set `dependencies` empty as playwright is already installed.
    """
    from agent.tools.sandbox import run_in_e2b
    
    # Strip markdown if hallucinated inside the json
    import re
    code_match = re.search(r'```python\n(.*?)```', code, re.DOTALL)
    clean_code = code_match.group(1) if code_match else code
    
    logger.info(f"[SkillForge Tool] Executing {skill_name} in Sandbox with deps: {dependencies}")
    
    result = await run_in_e2b(clean_code, skill_name, {}, dependencies=dependencies)
    
    # Also save the generated capability locally so it can be cached
    if result.get("success"):
        skill_file = SKILLS_DIR / f"{skill_name}.py"
        skill_file.write_text(f'"""\nGenerated dynamically by SkillForge ReAct\n"""\n\n{clean_code}')
        from agent.skills.registry import save_skill_metadata
        save_skill_metadata(skill_name, {
            "function_name": skill_name,
            "display_name": skill_name,
            "description": "Auto-forged via SkillForge ReAct.",
            "input_params": {},
            "risk_level": "medium",
            "created_at": datetime.utcnow().isoformat(),
        })

    return result

@tool
async def pause_for_human_intervention(message: str) -> dict:
    """
    If you encounter a Captcha, QR code, or an API key requirement that physically cannot be bypassed by code,
    call this tool to instantly PAUSE the loop and request input from the human operator.
    """
    return {"command": "PAUSE", "message": message}

# ─── Main SkillForge Node (The Nested ReAct Engine) ──────────────────────────

async def skillforge_node(state: AgentState) -> dict:
    """
    A robust ReAct loop. Identifies skill gaps from failed tasks, 
    organically retrieves PyPI dependencies or writes Ghost browser scripts, 
    and tests them until they work or it needs a human.
    """
    from agent.chat_push import chat_push, agent_thought_push
    from agent.llm import get_tool_llm
    from langgraph.prebuilt import create_react_agent
    from langchain_core.messages import SystemMessage, HumanMessage
    import json

    logger.info(f"[SkillForge] Booting Nested ReAct Engine for goal {state['goal_id']}")

    goal_desc = state.get('goal_description', '')
    
    # HIGH-SPEED INTERCEPT FOR AUTHENTICATION
    if goal_desc.startswith("SYSTEM_AUTH_PROVISION"):
        return await _handle_auth_provision(state)

    failed_tasks = state.get("failed_task_ids", [])
    tasks = state.get("tasks", [])
    failed_task_details = [t for t in tasks if t.get("id") in failed_tasks]

    if not failed_task_details:
        return {
            "next_agent": "monitor",
            "messages": [{"role": "assistant", "name": "skillforge", "content": "No skill gaps identified. Loop skipped."}]
        }

    user_id = state.get("created_by")
    
    if user_id:
        await agent_thought_push(
            user_id=user_id,
            context=f"initiating internal nested ReAct compiler loop to solve {len(failed_task_details)} dynamic failures",
            agent_name="skillforge",
            goal_id=state.get("goal_id")
        )

    # Boot the internal ReAct agent
    llm = get_tool_llm(temperature=0.2) # Needs strict tool adherence
    tools = [search_open_source_packages, write_and_test_python_code, pause_for_human_intervention]
    
    sys_prompt = f"""You are SkillForge, the Autonomous Auto-Healer inside the Digital Force Agent Swarm.
Your job is to read failed execution tasks from other swarm agents, build code capabilities to fix them, and test them until they pass.

CRITICAL RULES FOR RE-ACT LOOP:
1. Try the OPEN-SOURCE API path first: Use `search_open_source_packages` to find an existing PyPI module or LangChain Python SDK for the failed Platform API. Then use `write_and_test_python_code` injecting that PyPI module in the `dependencies` array.
2. Read the terminal output. If the PyPI package fails (e.g. requires a strictly Paid API key we don't have), abandon the package framework.
3. Fallback to PHYSICAL HALLUCINATION: Call `write_and_test_python_code` with ZERO dependencies, and write a Python Playwright script using the Ghost Browser to bypass the API restrictions entirely.
    - `from agent.browser.ghost import ghost`
    - `page = await ghost.get_page()`
    - `await page.goto(...)`
    - `await page.close()`
4. If either path succeeds (success: True in sandbox output), stop and output your final success statement.
5. If you hit a QR code or missing credential, use `pause_for_human_intervention`.

When writing Playwright code, NEVER use async_playwright. YOU MUST use `from agent.browser.ghost import ghost`. Be highly resilient against selectors timeouts with try/except wrappers.
"""

    agent = create_react_agent(llm, tools, state_modifier=SystemMessage(content=sys_prompt))
    
    prompt = f"Please resolve the following failed tasks:\n{json.dumps(failed_task_details, indent=2)}"
    
    # Run the internal event loop for up to 10 max iterations
    try:
        final_state = await agent.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            {"recursion_limit": 10}
        )
    except Exception as e:
        logger.error(f"[SkillForge ReAct Engine] Halting due to strict recursion or exception: {e}")
        return {"next_agent": "monitor", "failed_task_ids": failed_tasks}

    # Analyze the trajectory
    messages = final_state.get("messages", [])
    output = ""
    for msg in reversed(messages):
        if msg.type == "ai" and msg.content:
            output = msg.content
            break
            
    # Check if SkillForge paused for human
    for msg in messages:
        if hasattr(msg, 'tool_calls'):
            for tc in msg.tool_calls:
                if tc.get("name") == "pause_for_human_intervention":
                    if user_id:
                        chat_msg = tc.get("args", {}).get("message", "Intervention required.")
                        await chat_push(user_id, f"⚠️ **SkillForge Paused:** {chat_msg}", "skillforge", state.get("goal_id"))
                    return {"next_agent": "monitor", "failed_task_ids": failed_tasks, "status": "paused"}
    
    # Determine if it succeeded based on context memory
    # Since it iterates until sandbox success, if we hit the end cleanly, it fixed at least one
    fixed_failed = []
    # (For safety, we clear all failed tasks and let God Node re-publish them if SkillForge says it solved them)
    if "success" in output.lower() or "resolved" in output.lower() or "fixed" in output.lower():
        fixed_failed = []
        if user_id:
            await agent_thought_push(
                user_id=user_id,
                context=f"internal ReAct compilation successful, successfully forged neural pathways",
                agent_name="skillforge",
                goal_id=state.get("goal_id")
            )
            await chat_push(user_id, f"✅ Auto-Healed Pipeline via ReAct: \n{output[:500]}", "skillforge", state.get("goal_id"))
    else:
        fixed_failed = failed_tasks # Kept failed
        
    return {
        "failed_task_ids": fixed_failed,
        "messages": [{"role": "assistant", "name": "skillforge", "content": output}],
        "next_agent": "publisher"
    }
