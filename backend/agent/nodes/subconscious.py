"""
Digital Force — Subconscious Node
Injects background thoughts and campaign ideas into Qdrant for episodic memory,
and pushes high-relevance thoughts into chat.
"""

import json
import logging
from datetime import datetime
from agent.state import AgentState
from agent.chat_push import agent_thought_push, chat_push
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

async def subconscious_node(state: AgentState) -> dict:
    """
    Subconscious background thought cycle. 
    It reads recent_chats to contextualize the agent's background research.
    High value insights (>= 75%) are pushed to active chat.
    All insights are embedded into Qdrant.
    """
    recent_chats_raw = state.get("messages", [])
    past_campaigns = state.get("campaign_plan", {})
    industry = settings.industry
    user_id = state.get("created_by", "digital_force_admin")

    # Limit to recent 15 messages so the LLM has context of the ACTIVE conversation
    recent_chats = [{"role": msg.role, "content": msg.content} for msg in recent_chats_raw][-15:]
    
    # Render prompt
    chat_context = json.dumps(recent_chats, indent=2) if recent_chats else "No recent active chats."
    past_context = json.dumps(past_campaigns, indent=2) if past_campaigns else "No active campaigns currently."

    prompt = f"""
    You are the subconscious thought stream of a Digital Marketing Agentic Swarm for the {industry} industry.
    Currently, you are experiencing downtime. You must analyze the industry, review recent active chat discussions with the user, and generate a strategic insight.

    ## RECENT CHAT HISTORY
    {chat_context}

    ## RECENT CAMPAIGNS
    {past_context}

    Evaluate what the user is currently focused on, look for gaps in their current strategy, and uncover a high-leverage opportunity they might be missing.

    Return a JSON object with:
    1. "thought": The deep strategic insight (2-3 sentences).
    2. "relevance": A score from 0-100 indicating how urgently the user needs to hear this right now based on their chat history.
    3. "tags": 3-4 keywords categorizing the thought.
    """

    try:
        from agent.llm import generate_json
        from rag.pipeline import ingest_text
        
        result = await generate_json(
            messages=[
                {"role": "system", "content": "You are a proactive digital intelligence."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile"
        )
        
        thought = result.get("thought", "Analyzing system state.")
        relevance = result.get("relevance", 50)
        tags = result.get("tags", [])

        # Embed all thoughts into vector DB
        await ingest_text(
            text=thought,
            metadata={"source_type": "internal_thought", "tags": tags, "relevance": relevance},
            collection="knowledge"
        )
        logger.info(f"[Subconscious] Thought vectorized (Relevance: {relevance})")

        # Push to chat if it crosses the threshold
        if relevance >= 75:
            await agent_thought_push(
                user_id=user_id,
                context=f"formulated a high-priority subconscious insight (Relevance: {relevance})",
                agent_name="researcher",
                goal_id=None
            )
            await chat_push(
                user_id=user_id,
                content=f"🧠 **Spontaneous Insight:**\n\n{thought}"
            )
        
        return {"status": "ok", "subconscious_thought": thought}
    except Exception as e:
        logger.error(f"[Subconscious] Extraction error: {e}")
        return {"status": "error", "error": str(e)}
