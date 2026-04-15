"""
Digital Force — Agent Email Notification Utility

Agents use this to notify the user via email when:
  - A new API key is needed to unlock a capability
  - A high-risk action needs explicit approval
  - A campaign milestone is reached
  - An autonomous brief is ready

Uses the SMTP credentials already in .env (Gmail App Password supported).
"""

import logging
import smtplib
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
    to_email: Optional[str] = None,
) -> bool:
    """
    Send an email from Digital Force to the user.
    Falls back gracefully if SMTP is not configured.

    Returns True if sent successfully, False otherwise.
    """
    if not settings.smtp_username or not settings.smtp_password:
        logger.warning("[Email] SMTP not configured — skipping email notification")
        return False

    recipient = to_email or settings.smtp_username  # Default: email the user's own address

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Digital Force] {subject}"
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email or settings.smtp_username}>"
    msg["To"] = recipient

    # Plain text version
    msg.attach(MIMEText(body_text, "plain"))

    # HTML version (richer if provided)
    if body_html:
        msg.attach(MIMEText(body_html, "html"))
    else:
        # Auto-generate a clean HTML version from plain text
        html_body = _auto_html(subject, body_text)
        msg.attach(MIMEText(html_body, "html"))

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, msg, recipient)
        logger.info(f"[Email] ✅ Sent '{subject}' to {recipient}")
        return True
    except Exception as e:
        logger.error(f"[Email] Failed to send email: {e}")
        return False


def _smtp_send(msg: MIMEMultipart, recipient: str):
    """Blocking SMTP send — run in executor so it doesn't block the event loop."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(
            settings.smtp_from_email or settings.smtp_username,
            recipient,
            msg.as_string(),
        )


def _auto_html(subject: str, text: str) -> str:
    """Generate a clean branded HTML email from plain text."""
    paragraphs = "".join(
        f"<p style='margin:0 0 12px;line-height:1.6;'>{line}</p>"
        for line in text.split("\n")
        if line.strip()
    )
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d0d1a;font-family:Inter,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:40px 20px;">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#13131f;border-radius:16px;border:1px solid rgba(255,255,255,0.08);overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:28px 32px;background:linear-gradient(135deg,#7C3AED22,#22D3EE11);border-bottom:1px solid rgba(255,255,255,0.06);">
              <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:1.1rem;font-weight:700;color:#fff;">⚡ Digital Force</span>
                <span style="font-size:0.75rem;color:rgba(255,255,255,0.35);margin-left:8px;">Autonomous Agency</span>
              </div>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 20px;font-size:1.15rem;font-weight:600;color:#fff;">{subject}</h2>
              <div style="color:rgba(255,255,255,0.7);font-size:0.9rem;">
                {paragraphs}
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.06);">
              <p style="margin:0;font-size:0.75rem;color:rgba(255,255,255,0.25);">
                This message was sent autonomously by your Digital Force agents.<br>
                Reply to this email or open your dashboard to respond.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


# ─── Specialised agent-level helpers ─────────────────────────────────────────

async def notify_api_key_needed(
    capability: str,
    api_name: str,
    signup_url: str,
    why_needed: str,
    is_free: bool,
    user_email: Optional[str] = None,
) -> bool:
    """
    Notify via email when an agent needs a new API credential.
    Also returns the message text so the caller can push it to chat.
    """
    free_note = "✅ Free tier available — no credit card needed." if is_free else "⚠️ Paid API — check pricing before signing up."
    subject = f"Action Required: API Key Needed for {capability}"
    body = f"""Your Digital Force agents want to unlock a new capability: {capability}

Why this is needed:
{why_needed}

API Required: {api_name}
{free_note}

Sign up here: {signup_url}

Once you have the key:
1. Go to your Digital Force dashboard → Settings → Integrations
2. Add the key in the relevant field
3. Your agents will automatically pick it up and retry the task

This capability will permanently expand what your agency can do.

— Your Digital Force Agents"""

    return await send_agent_email(subject, body, to_email=user_email)


async def notify_high_risk_approval(
    action_description: str,
    risk_reason: str,
    skill_name: str,
    user_email: Optional[str] = None,
) -> bool:
    """
    Email the user when SkillForge has forged a high-risk skill and needs approval.
    """
    subject = f"Approval Required: {action_description}"
    body = f"""Your Digital Force agents have forged a solution to a problem they encountered, but need your approval before proceeding.

Action: {action_description}

Why approval is needed:
{risk_reason}

Skill created: {skill_name}

To approve: Open your Digital Force chat and reply 'approve' or 'go ahead'.
To skip: Reply 'skip' or 'drop it'.

If you ignore this, the task will remain paused until you respond.

— Your Digital Force Agents"""

    return await send_agent_email(subject, body, to_email=user_email)


async def notify_campaign_complete(
    campaign_title: str,
    summary: str,
    metrics: dict,
    user_email: Optional[str] = None,
) -> bool:
    """Email summary when a campaign finishes."""
    subject = f"Campaign Complete: {campaign_title}"
    metrics_text = "\n".join([f"  • {k}: {v}" for k, v in metrics.items()]) or "  No metrics yet."
    body = f"""Your campaign has completed.

Campaign: {campaign_title}

Summary:
{summary}

Results:
{metrics_text}

Open your Digital Force dashboard to see full analytics.

— Your Digital Force Agents"""

    return await send_agent_email(subject, body, to_email=user_email)
