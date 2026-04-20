"""
Digital Force — Agent Email Notification Utility

Sends branded HTML emails FROM digitalforce1st@gmail.com TO digitalforce1st@gmail.com
(Reply-To is set so replies come back to the same inbox for polling).

Each approval email embeds a unique token in the subject line:
  [Digital Force | Ref: <token>]

The inbox poller (email_inbox.py) reads replies, matches the token,
and triggers the appropriate agent action.
"""

import logging
import uuid
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()




async def send_agent_email(
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    approval_token: Optional[str] = None,
    to_email: Optional[str] = None,
) -> bool:
    """
    Send an email to the user's inbox.
    If approval_token is provided, it's embedded in the subject for reply matching.
    """
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("[Email] SMTP not configured — skipping")
        return False

    recipient = to_email or settings.smtp_username
    if not recipient:
        return False

    full_subject = f"[Digital Force] {subject}"
    if approval_token:
        full_subject += f" | Ref: {approval_token}"

    email_from = settings.smtp_from_email or settings.smtp_username
    email_from_name = settings.smtp_from_name or "Digital Force"

    msg = MIMEMultipart("alternative")
    msg["Subject"]  = full_subject
    msg["From"]     = f"{email_from_name} <{email_from}>"
    msg["To"]       = recipient
    msg["Reply-To"] = email_from  # Replies come back to the FROM inbox for IMAP polling

    msg.attach(MIMEText(body_text, "plain"))
    html = body_html or f"<html><body><pre>{body_text}</pre></body></html>"
    msg.attach(MIMEText(html, "html"))

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, msg, recipient, email_from)
        logger.info(f"[Email] ✅ Sent '{full_subject}' to {recipient}")
        return True
    except Exception as e:
        logger.error(f"[Email] Failed: {e}")
        return False


def _smtp_send(msg: MIMEMultipart, recipient: str, email_from: str):
    import smtplib
    try:
        with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port)) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password.replace(" ", ""))
            
            # Remove any asterisks from the payload to prevent raw markdown rendering
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    part.set_payload(part.get_payload().replace("**", "").replace("*", ""))
                elif part.get_content_type() == "text/html":
                    part.set_payload(part.get_payload().replace("**", "").replace("*", ""))
            
            server.sendmail(email_from, recipient, msg.as_string())
    except Exception as e:
        logger.error(f"[Email] SMTP internal error: {e}")
        raise e


async def _generate_neural_email(context: str, user_id: str, token: Optional[str] = None) -> dict:
    from agent.llm import generate_json
    try:
        from database import async_session, AgencySettings
        from sqlalchemy import select
        async with async_session() as session:
            stmt = select(AgencySettings.agent_tone).where(AgencySettings.user_id == user_id)
            tone = (await session.execute(stmt)).scalar_one_or_none() or "Professional"
    except Exception:
        tone = "Professional"

    system = f"You are the autonomous Digital Force AI. Tone: {tone}. Craft an elite, responsive HTML email for a client."
    prompt = f"""
CONTEXT TO COMMUNICATE:
{context}

{'IMPORTANT: They must reply to this email with "approve" or "skip" (reference token: ' + token + '). Highlight this.' if token else ''}

Return JSON ONLY:
{{
  "subject": "Engaging subject line",
  "text": "Plain text version",
  "html": "Aesthetically pleasing HTML email. Use inline CSS, dark theme (#0d0d1a bg), and modern fonts (Inter/sans-serif). Keep it professional but highly elite."
}}
"""
    try:
        return await generate_json(prompt, system)
    except Exception as e:
        logger.error(f"Neural email generation failed: {e}")
        return {
            "subject": "Digital Force Notification",
            "text": context,
            "html": f"<html><body><p>{context}</p></body></html>"
        }


# ─── Specialised helpers ──────────────────────────────────────────────────────

async def _get_user_email(user_id: str) -> Optional[str]:
    target_emails = settings.target_notification_emails
    if target_emails:
        return target_emails.split(',')[0].strip()

    if not user_id:
        return None
    try:
        from database import async_session, User
        from sqlalchemy import select
        async with async_session() as session:
            stmt = select(User.email).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"[Email] Failed to fetch user email: {e}")
        return None


async def notify_api_key_needed(
    capability: str,
    api_name: str,
    signup_url: str,
    why_needed: str,
    is_free: bool,
    user_id: str = "",
    goal_id: str = "",
) -> Optional[str]:
    """
    Notify about a missing API credential.
    Returns the approval token (stored in DB by caller).
    """
    token = str(uuid.uuid4())[:8].upper()
    email_data = await _generate_neural_email(
        context=f"We need an API credential ({api_name}) to execute: {capability}. Why: {why_needed}. Is free: {is_free}. Sign up URL: {signup_url}. Tell them to add the key in Settings -> Integrations so we can retry automatically.",
        user_id=user_id,
        token=token
    )
    
    to_email = await _get_user_email(user_id)
    await send_agent_email(email_data["subject"], email_data["text"], email_data["html"], approval_token=token, to_email=to_email)
    return token


async def notify_high_risk_approval(
    action_description: str,
    risk_reason: str,
    skill_name: str,
    user_id: str = "",
    goal_id: str = "",
) -> Optional[str]:
    """
    Email user for high-risk approval. Returns the token stored in PendingEmailApproval.
    """
    token = str(uuid.uuid4())[:8].upper()
    
    email_data = await _generate_neural_email(
        context=f"We built a high-risk fix ({skill_name}) for a roadblock. Action: {action_description}. Risk reason: {risk_reason}. We need their explicit approval to execute.",
        user_id=user_id,
        token=token
    )

    # Store in DB so inbox poller can match replies
    try:
        from database import PendingEmailApproval, async_session
        from datetime import timedelta
        async with async_session() as session:
            session.add(PendingEmailApproval(
                id=str(uuid.uuid4()),
                token=token,
                user_id=user_id,
                action_type="high_risk",
                skill_name=skill_name,
                goal_id=goal_id,
                description=action_description,
                expires_at=datetime.utcnow() + timedelta(hours=48),
            ))
            await session.commit()
    except Exception as e:
        logger.error(f"[Email] Could not store pending approval: {e}")

    to_email = await _get_user_email(user_id)
    await send_agent_email(email_data["subject"], email_data["text"], email_data["html"], approval_token=token, to_email=to_email)
    return token


async def notify_campaign_complete(
    campaign_title: str,
    summary: str,
    metrics: dict,
    user_id: str = "",
) -> bool:
    to_email = await _get_user_email(user_id)
    metrics_text = ", ".join([f"{k}: {v}" for k, v in metrics.items()]) or "No metrics"
    email_data = await _generate_neural_email(
        context=f"The campaign '{campaign_title}' has completed! Summary: {summary}. Metrics: {metrics_text}. Tell the user to check their dashboard.",
        user_id=user_id
    )
    return await send_agent_email(email_data["subject"], email_data["text"], email_data["html"], to_email=to_email)
