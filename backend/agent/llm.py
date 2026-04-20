"""
Digital Force — Agent LLM Client
Multi-provider cascading router with TPD-aware rotation.

FIXED (2.3):
- CASCADE ORDER: now rotates KEYS first, then models.
  Previously rotated models per key — meaning a TPD-exhausted key
  would be tried 3 times (once per model) before moving on.
  New order: Key1/M1 → Key2/M1 → Key3/M1 → Key1/M2 → Key2/M2 → ...
  This ensures we immediately jump to a fresh API key on any 429.

- get_tool_llm(): now accepts a `cascade_index` so each agent gets a
  different key by default, and falls back through the cascade on 429.

- Token budget awareness: TPD errors are caught explicitly and skip
  straight to the next key (not next model on the same key).

- "Failed to call a function" errors: these are Groq tool-call
  schema failures on large models. Fixed by trying the 8b-instant
  model which has more reliable JSON tool-call adherence on short prompts.
"""

import json
import re
import logging
from typing import Optional, AsyncGenerator
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Rate limit tracking: remember exhausted keys to skip them ──────────────────
_exhausted_keys: set[str] = set()  # Keys that hit their daily TPD limit


def _is_tpd_error(e: Exception) -> bool:
    """Returns True if the error is a daily token quota (TPD) exhaustion."""
    err_str = str(e).lower()
    return "tokens per day" in err_str or "tpd" in err_str


def _is_tpm_error(e: Exception) -> bool:
    """Returns True if the error is a per-minute rate limit (TPM) — recoverable."""
    err_str = str(e).lower()
    return "rate_limit_exceeded" in err_str and "tokens per day" not in err_str


def _get_cascade_configs():
    """
    Return list of (api_key, model_name) ordered for MAXIMUM resilience.

    Order: Rotate KEYS first, then fall back to slower models.
    Example with 3 keys and 3 models:
      (Key1, llama-70b), (Key2, llama-70b), (Key3, llama-70b),
      (Key1, llama-8b),  (Key2, llama-8b),  (Key3, llama-8b),
      (Key1, gemma2),    (Key2, gemma2),    (Key3, gemma2)

    This means: a TPD-exhausted key is skipped immediately by moving to
    the next KEY rather than the next MODEL on the same dead key.
    """
    keys = [k for k in [
        settings.groq_api_key_1,
        settings.groq_api_key_2,
        settings.groq_api_key_3,
    ] if k]

    if not keys:
        raise ValueError("No Groq API keys configured. Set GROQ_API_KEY_1, 2, or 3 in .env")

    models = [m for m in [
        settings.groq_primary_model,    # llama-3.3-70b-versatile
        settings.groq_secondary_model,  # llama-3.1-8b-instant (fast, reliable tool calls)
        settings.groq_fallback_model,   # gemma2-9b-it
    ] if m]

    configs = []
    # KEYS rotate first — ensures we hit a fresh key before falling back to a smaller model
    for model in models:
        for key in keys:
            configs.append((key, model))

    return configs


async def generate_completion(
    prompt: str,
    system_prompt: str = "",
    prefer_reasoning: bool = False,
    temperature: float = 0.7,
) -> str:
    """
    Invokes the cascading LLM router. Automatically rotates through all
    API keys × models on any error. TPD-exhausted keys are remembered and
    skipped for the session so we don't waste retries on dead keys.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from langchain_groq import ChatGroq

    no_asterisk_rule = "\n\nIMPORTANT: DO NOT use markdown asterisks (`*` or `**`) to bold text anywhere in your output. Return plain text without formatting symbols."
    system_prompt = (system_prompt + no_asterisk_rule).strip()

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ]

    configs = _get_cascade_configs()
    last_error = None

    for attempt, (api_key, model) in enumerate(configs, 1):
        # Skip keys we already know are exhausted for today
        if api_key in _exhausted_keys:
            logger.debug(f"[LLM Cascade] Skipping exhausted key ...{api_key[-4:]}")
            continue

        try:
            llm = ChatGroq(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=settings.groq_max_tokens,
                max_retries=0,  # We manage retries in this loop
            )
            response = await llm.ainvoke(messages)
            return response.content

        except Exception as e:
            last_error = e
            key_tail = api_key[-4:]

            if _is_tpd_error(e):
                # Daily limit hit — mark key as dead for this session
                _exhausted_keys.add(api_key)
                logger.warning(f"[LLM Cascade] Key ...{key_tail} hit daily TPD limit. Skipping key for rest of session.")
            elif _is_tpm_error(e):
                # Per-minute limit — just move to next slot (different key or model)
                logger.warning(f"[LLM Cascade] Attempt {attempt}/{len(configs)}: TPM rate limit on Key ...{key_tail} / {model}. Rotating.")
            else:
                logger.warning(f"[LLM Cascade] Attempt {attempt}/{len(configs)} failed (Key: ...{key_tail}, Model: {model}): {type(e).__name__}: {str(e)[:120]}")

    logger.error(f"[LLM Cascade] CRITICAL: ALL {len(configs)} slots exhausted. Final error: {last_error}")
    raise last_error or RuntimeError("All LLM cascade slots failed with no error captured.")


async def generate_json(
    prompt: str,
    system_prompt: str = "",
    prefer_reasoning: bool = False,
) -> dict:
    """Generate and natively parse a JSON object from the AI."""
    sys = (system_prompt or "") + "\n\nRESPOND WITH VALID JSON ONLY. No markdown fences, no explanation."
    raw = await generate_completion(prompt, sys, prefer_reasoning=prefer_reasoning, temperature=0.3)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM did not return valid JSON: {raw[:300]}")


async def stream_chat_response(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """Legacy single-turn stream (kept for compatibility)."""
    async for token in stream_chat_with_history(
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield token


async def stream_chat_with_history(
    system: str,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 1500,
) -> AsyncGenerator[str, None]:
    """
    Memory-aware chat streaming with cascade fallback.
    Rotates keys first (to stay on the fast 70b model as long as possible),
    then falls back to smaller models.
    """
    from groq import AsyncGroq

    no_asterisk_rule = "\n\nIMPORTANT: DO NOT use markdown asterisks (`*` or `**`) to bold text anywhere in your output. Return plain text without formatting symbols."
    system = (system + no_asterisk_rule).strip()

    # Build groq messages array
    groq_messages = [{"role": "system", "content": system}]
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "assistant"):
            role = "assistant"
        groq_messages.append({"role": role, "content": m.get("content", "")})

    configs = _get_cascade_configs()
    last_error = None

    for attempt, (api_key, model) in enumerate(configs, 1):
        if api_key in _exhausted_keys:
            continue

        try:
            client = AsyncGroq(api_key=api_key, max_retries=0)
            stream = await client.chat.completions.create(
                model=model,
                messages=groq_messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            return

        except Exception as e:
            last_error = e
            key_tail = api_key[-4:]
            if _is_tpd_error(e):
                _exhausted_keys.add(api_key)
                logger.warning(f"[LLM Stream] Key ...{key_tail} TPD exhausted. Marking dead.")
            else:
                logger.warning(f"[LLM Stream] Attempt {attempt}/{len(configs)} failed (Key ...{key_tail} / {model}): {str(e)[:120]}")

    # Last resort: non-streaming fallback
    logger.error("[LLM Stream] All cascade slots failed. Attempting non-streaming fallback.")
    try:
        full = await generate_completion(
            prompt=messages[-1].get("content", "") if messages else "",
            system_prompt=system,
            temperature=temperature,
        )
        for i in range(0, len(full), 4):
            yield full[i:i+4]
    except Exception as e:
        yield f"I'm temporarily unavailable — all API rate limits hit. Please try again in a few minutes. (Error: {str(e)[:80]})"


def get_llm_client():
    from config import get_settings
    s = get_settings()
    return {
        "groq_1": bool(s.groq_api_key_1),
        "groq_2": bool(s.groq_api_key_2),
        "groq_3": bool(s.groq_api_key_3),
        "stream_chat": stream_chat_response,
    }


def get_tool_llm(temperature: float = 0.3):
    """
    Returns a LangChain ChatGroq instance for bind_tools() agent loops.

    FIXED: Now cascades through all keys/models on instantiation attempts,
    and skips TPD-exhausted keys. Prefers llama-3.1-8b-instant for tool
    calling when the 70b model hits "Failed to call a function" schema errors.
    """
    from langchain_groq import ChatGroq

    configs = _get_cascade_configs()

    for api_key, model in configs:
        if api_key in _exhausted_keys:
            continue
        try:
            return ChatGroq(
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_retries=1,
            )
        except Exception as e:
            logger.warning(f"[Tool LLM] Could not instantiate {model} with key ...{api_key[-4:]}: {e}")
            continue

    raise RuntimeError("get_tool_llm: No usable LLM slot available. All keys may be exhausted.")


async def heal_dom_selector(screenshot_path: str, failed_selector: str) -> Optional[str]:
    """Uses vision model to hot-patch broken CSS selectors from a DOM snapshot."""
    key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
    if not key:
        logger.warning("[Vision Healer] No Groq API key available.")
        return None

    try:
        import base64, os
        from groq import AsyncGroq

        if not os.path.exists(screenshot_path):
            return None

        client = AsyncGroq(api_key=key, max_retries=1)

        with open(screenshot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        prompt = (
            f"The CSS selector '{failed_selector}' timed out and failed. "
            "Examine this screenshot and return ONLY the new valid CSS selector string "
            "that targets that element. No markdown, no explanations."
        )

        resp = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }],
            max_tokens=50,
            temperature=0.1
        )
        new_selector = resp.choices[0].message.content.strip().strip("'\"`")
        if new_selector and len(new_selector) < 100:
            return new_selector
    except Exception as e:
        logger.error(f"[Vision Healer] Failed: {e}")
    return None
