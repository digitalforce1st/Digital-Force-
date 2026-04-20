"""
Digital Force — Multi-Provider LLM Router
==========================================
Honest capacity math:
  Groq free:        100k tokens/day/key × 3 keys = 300k tokens/day
  1 content piece:  ~1,500 tokens = 200 pieces/day on Groq alone
  OpenAI GPT-4o-mini: 10M tokens/day (paid) = effectively unlimited
  Together AI:      Parallel inference, 100+ models, cheap

To do what 100 people do in a week in a single day, we need:
  - Groq:       Fast, free, rate-limited  → use for high-volume generation
  - OpenAI:     Reliable, paid, high-cap  → use when Groq is exhausted
  - Together:   Cheap parallel inference  → batch generation at scale
  - Gemini:     Google's free tier        → additional free capacity

ROUTING STRATEGY:
  1. Try Groq first (free, fast)
  2. On TPD exhaustion → OpenAI (gpt-4o-mini, cheap, high-cap)
  3. On OpenAI failure → Together AI (Llama 3.3 70b, very cheap)
  4. On Together failure → Gemini (free tier backup)
  5. Stream always: Groq for chat (speed matters), OpenAI for agent loops

The cascade now spans PROVIDERS not just keys, giving essentially
unlimited capacity for high-volume autonomous campaigns.
"""

import json
import re
import logging
import asyncio
from typing import Optional, AsyncGenerator
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Session-level exhausted key tracking ────────────────────────────────────
_exhausted_keys: set[str] = set()


def _is_tpd_error(e: Exception) -> bool:
    err = str(e).lower()
    return "tokens per day" in err or "tpd" in err or "daily" in err and "limit" in err


def _is_rate_error(e: Exception) -> bool:
    err = str(e).lower()
    return "rate_limit" in err or "429" in err or "too many" in err


# ── Provider Configs ──────────────────────────────────────────────────────────

def _get_groq_configs():
    """
    Dynamically build the Groq cascade from ALL configured keys.
    Works with 1, 3, 5, or 10 keys — just add GROQ_API_KEY_N to .env.

    With 10 keys × 3 models = 30 cascade slots, 1M tokens/day.
    Order: all keys on model 1 → all keys on model 2 → all keys on model 3
    This keeps us on the fastest (70b) model as long as possible.
    """
    keys = settings.all_groq_keys  # Uses the new property — picks up all 10
    if not keys:
        return []

    models = [m for m in [
        settings.groq_primary_model,    # llama-3.3-70b-versatile (quality)
        settings.groq_secondary_model,  # llama-3.1-8b-instant (speed)
        settings.groq_fallback_model,   # gemma2-9b-it (stable)
    ] if m]

    # For N keys × 3 models: rotate ALL keys per model tier
    # Key1/70b, Key2/70b, ..., Key10/70b → Key1/8b, Key2/8b, ..., Key10/8b → etc.
    configs = []
    for model in models:
        for key in keys:
            configs.append(("groq", key, model))

    logger.info(f"[LLM] Groq cascade: {len(keys)} key(s) × {len(models)} models = {len(configs)} slots | ~{len(keys) * 100_000:,} tokens/day")
    return configs


def _get_openai_configs():
    key = getattr(settings, "openai_api_key", "")
    if not key:
        return []
    return [
        ("openai", key, "gpt-4o-mini"),   # Cheapest, high capacity
        ("openai", key, "gpt-4o"),        # Quality fallback
    ]


def _get_together_configs():
    key = getattr(settings, "together_api_key", "")
    if not key:
        return []
    return [
        ("together", key, "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
        ("together", key, "meta-llama/Llama-3.1-8B-Instruct-Turbo"),
    ]


def _get_gemini_configs():
    key = getattr(settings, "gemini_api_key", "")
    if not key:
        return []
    return [
        ("gemini", key, "gemini-1.5-flash"),   # Fast, high daily quota (free)
        ("gemini", key, "gemini-1.5-pro"),     # Quality backup
    ]


def _get_full_cascade():
    """
    Build the complete provider cascade.
    Order: Groq (free, fast) → OpenAI (paid, reliable) → Together (cheap bulk) → Gemini (free backup)
    """
    cascade = []
    cascade.extend(_get_groq_configs())
    cascade.extend(_get_openai_configs())
    cascade.extend(_get_together_configs())
    cascade.extend(_get_gemini_configs())
    return cascade


async def _invoke_provider(provider: str, api_key: str, model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """Universal provider invoker — handles Groq, OpenAI, Together, Gemini APIs."""
    no_asterisk = "\n\nNever use markdown asterisks (**bold** or *italic*) in your response. Plain text only."

    # Inject no-asterisk rule into system message
    enriched = []
    for m in messages:
        if m["role"] == "system":
            enriched.append({"role": "system", "content": m["content"] + no_asterisk})
        else:
            enriched.append(m)

    if provider == "groq":
        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key, max_retries=0)
        resp = await client.chat.completions.create(
            model=model, messages=enriched,
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    elif provider == "openai":
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": enriched, "temperature": temperature, "max_tokens": max_tokens},
            )
            data = resp.json()
            if "error" in data:
                raise Exception(data["error"].get("message", str(data["error"])))
            return data["choices"][0]["message"]["content"]

    elif provider == "together":
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": enriched, "temperature": temperature, "max_tokens": max_tokens},
            )
            data = resp.json()
            if "error" in data:
                raise Exception(str(data["error"]))
            return data["choices"][0]["message"]["content"]

    elif provider == "gemini":
        import httpx
        # Convert to Gemini format
        gemini_parts = []
        system_text = ""
        for m in enriched:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                gemini_parts.append({"role": "user" if m["role"] == "user" else "model",
                                     "parts": [{"text": m["content"]}]})
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                json={
                    "system_instruction": {"parts": [{"text": system_text}]} if system_text else None,
                    "contents": gemini_parts,
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                },
            )
            data = resp.json()
            if "error" in data:
                raise Exception(data["error"].get("message", str(data)))
            return data["candidates"][0]["content"]["parts"][0]["text"]

    raise ValueError(f"Unknown provider: {provider}")


async def _stream_provider(provider: str, api_key: str, model: str, messages: list, temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
    """Streaming version for chat interface."""
    if provider == "groq":
        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key, max_retries=0)
        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True,
            temperature=temperature, max_tokens=max_tokens,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        return

    elif provider == "openai":
        import httpx
        no_asterisk = "\n\nNever use markdown asterisks in your response."
        enriched = [{"role": m["role"], "content": m["content"] + no_asterisk if m["role"] == "system" else m["content"]} for m in messages]
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": enriched, "temperature": temperature, "max_tokens": max_tokens, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass
        return

    # Fallback: non-streaming
    full = await _invoke_provider(provider, api_key, model, messages, temperature, max_tokens)
    for i in range(0, len(full), 4):
        yield full[i:i+4]


# ── Public API ─────────────────────────────────────────────────────────────────

async def generate_completion(
    prompt: str,
    system_prompt: str = "",
    prefer_reasoning: bool = False,
    temperature: float = 0.7,
) -> str:
    """Full cascade: Groq → OpenAI → Together → Gemini. Never fails silently."""
    messages = [
        {"role": "system", "content": system_prompt or "You are a helpful assistant."},
        {"role": "user", "content": prompt},
    ]
    cascade = _get_full_cascade()
    last_error = None

    for provider, api_key, model in cascade:
        if api_key in _exhausted_keys:
            continue
        try:
            result = await _invoke_provider(provider, api_key, model, messages, temperature, min(4096, 4096))
            if attempt_count := getattr(generate_completion, "_attempt_count", 0):
                pass  # Not tracking globally but could log
            return result
        except Exception as e:
            last_error = e
            if _is_tpd_error(e):
                _exhausted_keys.add(api_key)
                logger.warning(f"[LLM] {provider}/{model} TPD exhausted. Moving to next provider.")
            elif _is_rate_error(e):
                logger.warning(f"[LLM] {provider}/{model} rate limited. Rotating.")
            else:
                logger.warning(f"[LLM] {provider}/{model} error: {str(e)[:100]}")

    raise last_error or RuntimeError("All LLM providers failed.")


async def generate_completion_batch(
    prompts: list[tuple[str, str]],
    temperature: float = 0.7,
    max_concurrent: int = 20,
) -> list[str]:
    """
    Generate completions for MULTIPLE prompts in parallel.
    This is the swarm's secret weapon — instead of generating content one at a time,
    generate 50 pieces of content simultaneously.

    Args:
        prompts: List of (prompt, system_prompt) tuples
        max_concurrent: Max parallel LLM calls (default 20 — tune based on API limits)

    Returns:
        List of completions in the same order as prompts
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _guarded(prompt: str, system: str) -> str:
        async with semaphore:
            return await generate_completion(prompt, system, temperature=temperature)

    results = await asyncio.gather(
        *[_guarded(p, s) for p, s in prompts],
        return_exceptions=True,
    )
    # Replace exceptions with error strings
    return [r if isinstance(r, str) else f"ERROR: {r}" for r in results]


async def generate_json(prompt: str, system_prompt: str = "", prefer_reasoning: bool = False) -> dict:
    sys = (system_prompt or "") + "\n\nRESPOND WITH VALID JSON ONLY. No markdown fences, no explanation."
    raw = await generate_completion(prompt, sys, temperature=0.3)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM did not return valid JSON: {raw[:300]}")


async def stream_chat_with_history(
    system: str,
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 1500,
) -> AsyncGenerator[str, None]:
    """Streaming multi-turn chat. Cascades across all providers."""
    no_asterisk = "\n\nNever use markdown asterisks (**bold** or *italic*) in your response. Plain text only."
    system = (system + no_asterisk).strip()

    groq_messages = [{"role": "system", "content": system}]
    for m in messages:
        role = m.get("role", "user")
        if role not in ("user", "assistant"):
            role = "assistant"
        groq_messages.append({"role": role, "content": m.get("content", "")})

    cascade = _get_full_cascade()
    last_error = None

    for provider, api_key, model in cascade:
        if api_key in _exhausted_keys:
            continue
        try:
            async for token in _stream_provider(provider, api_key, model, groq_messages, temperature, max_tokens):
                yield token
            return
        except Exception as e:
            last_error = e
            if _is_tpd_error(e):
                _exhausted_keys.add(api_key)
                logger.warning(f"[LLM Stream] {provider} TPD hit. Rotating provider.")
            else:
                logger.warning(f"[LLM Stream] {provider}/{model}: {str(e)[:100]}")

    yield "All AI providers temporarily unavailable. Please try again in a few minutes."


async def stream_chat_response(system: str, user: str, temperature: float = 0.7, max_tokens: int = 1024) -> AsyncGenerator[str, None]:
    async for token in stream_chat_with_history(system=system, messages=[{"role": "user", "content": user}], temperature=temperature, max_tokens=max_tokens):
        yield token


def get_tool_llm(temperature: float = 0.3):
    """LangChain-compatible LLM for ReAct agents. Cascades providers."""
    # Try Groq first (best tool-call support with LangChain)
    groq_configs = _get_groq_configs()
    for _, api_key, model in groq_configs:
        if api_key in _exhausted_keys:
            continue
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(model=model, api_key=api_key, temperature=temperature, max_retries=1)
        except Exception as e:
            logger.warning(f"[Tool LLM] Groq {model} failed: {e}")

    # Try OpenAI (also has excellent tool-call support)
    openai_key = getattr(settings, "openai_api_key", "")
    if openai_key and openai_key not in _exhausted_keys:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=temperature)
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"[Tool LLM] OpenAI failed: {e}")

    raise RuntimeError("get_tool_llm: All providers exhausted.")


def get_llm_client():
    from config import get_settings
    s = get_settings()
    return {
        "groq_1": bool(s.groq_api_key_1),
        "groq_2": bool(s.groq_api_key_2),
        "groq_3": bool(s.groq_api_key_3),
        "openai": bool(getattr(s, "openai_api_key", "")),
        "together": bool(getattr(s, "together_api_key", "")),
        "gemini": bool(getattr(s, "gemini_api_key", "")),
        "stream_chat": stream_chat_response,
    }


async def heal_dom_selector(screenshot_path: str, failed_selector: str) -> Optional[str]:
    """Vision model to hot-patch broken CSS selectors."""
    import base64, os
    key = settings.groq_api_key_1 or settings.groq_api_key_2 or settings.groq_api_key_3
    if not key or not os.path.exists(screenshot_path):
        return None
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=key, max_retries=1)
        with open(screenshot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        prompt = (f"The CSS selector '{failed_selector}' failed on this page. "
                  "Return ONLY the new valid CSS selector. No markdown, no explanation.")
        resp = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]}],
            max_tokens=50, temperature=0.1
        )
        sel = resp.choices[0].message.content.strip().strip("'\"`")
        return sel if sel and len(sel) < 100 else None
    except Exception as e:
        logger.error(f"[Vision Healer] {e}")
    return None
