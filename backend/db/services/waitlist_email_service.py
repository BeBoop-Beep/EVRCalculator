"""Waitlist verification email dispatch module.

This module is intentionally isolated to waitlist workflows.
When no email provider is configured, it acts as a no-op/stub that logs
non-sensitive diagnostics.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)



def _redacted_url(url: str) -> str:
    parts = urlsplit(url)
    # Never log query params because they contain raw verification tokens.
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _build_waitlist_email_html(verification_url: str, frontend_base_url: str) -> str:
        return f"""
<div style=\"font-family: Arial, sans-serif; color: #0f172a; line-height: 1.5;\">
    <h2 style=\"margin: 0 0 12px;\">Confirm your spot on the inDex waitlist</h2>
    <p style=\"margin: 0 0 16px;\">Click the button below to verify your email and confirm your spot.</p>
    <p style=\"margin: 0 0 20px;\">
        <a href=\"{verification_url}\" style=\"display: inline-block; background: #0f172a; color: #ffffff; text-decoration: none; padding: 10px 16px; border-radius: 6px;\">Verify my email</a>
    </p>
    <p style=\"margin: 0 0 8px;\">This verification link expires in 24 hours.</p>
    <p style=\"margin: 0; color: #475569; font-size: 13px;\">If the button does not work, copy and paste this URL in your browser:</p>
    <p style=\"margin: 6px 0 0; color: #1d4ed8; font-size: 13px; word-break: break-all;\">{verification_url}</p>
    <p style=\"margin: 18px 0 0; color: #475569; font-size: 13px;\">inDex Team • {frontend_base_url}</p>
</div>
""".strip()



def send_waitlist_verification_email(
    recipient_email: str,
    verification_url: str,
    source: str,
) -> bool | dict:
    """Send waitlist verification email (stub if provider is not configured)."""
    provider = (os.getenv("WAITLIST_EMAIL_PROVIDER") or "").strip().lower()
    redacted_url = _redacted_url(verification_url)

    if not provider:
        logger.info(
            "waitlist_email: provider not configured; verification email stubbed recipient=%s source=%s url=%s",
            recipient_email,
            source,
            redacted_url,
        )
        return True

    if provider != "resend":
        logger.info(
            "waitlist_email: unsupported provider=%s; verification email stubbed recipient=%s source=%s url=%s",
            provider,
            recipient_email,
            source,
            redacted_url,
        )
        return True

    resend_api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not resend_api_key:
        logger.error(
            "waitlist_email: provider=resend but RESEND_API_KEY is missing recipient=%s source=%s",
            recipient_email,
            source,
        )
        return False

    resend_from_email = (os.getenv("RESEND_FROM_EMAIL") or "").strip()
    node_env = (os.getenv("NODE_ENV") or "").strip().lower()

    logger.info(
        "[waitlist] email config %s",
        {
            "hasResendKey": bool(os.getenv("RESEND_API_KEY")),
            "hasFromEmail": bool(os.getenv("RESEND_FROM_EMAIL")),
            "fromEmail": os.getenv("RESEND_FROM_EMAIL"),
            "nodeEnv": os.getenv("NODE_ENV"),
        },
    )

    if not resend_from_email:
        if node_env == "production":
            logger.error(
                "waitlist_email: provider=resend but RESEND_FROM_EMAIL is missing in production recipient=%s source=%s",
                recipient_email,
                source,
            )
            return {
                "ok": False,
                "code": "email_config_missing",
                "message": "Verification email sender is not configured.",
            }
        resend_from_email = "inDex <onboarding@resend.dev>"

    frontend_base_url = (os.getenv("FRONTEND_BASE_URL") or "").strip()
    if not frontend_base_url:
        parts = urlsplit(verification_url)
        frontend_base_url = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""

    payload = {
        "from": resend_from_email,
        "to": [recipient_email],
        "subject": "Confirm your spot on the inDex waitlist",
        "html": _build_waitlist_email_html(verification_url, frontend_base_url),
    }

    headers = {
        "Authorization": f"Bearer {resend_api_key}",
        "Content-Type": "application/json",
    }

    try:
        logger.info(
            "waitlist_email: sending provider=resend recipient=%s source=%s",
            recipient_email,
            source,
        )
        response = requests.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=payload,
            timeout=15,
        )
        if 200 <= response.status_code < 300:
            logger.info(
                "waitlist_email: send_success provider=resend recipient=%s source=%s",
                recipient_email,
                source,
            )
            return True

        logger.error(
            "waitlist_email: send_failed provider=resend recipient=%s source=%s status=%s body=%s url=%s",
            recipient_email,
            source,
            response.status_code,
            response.text,
            redacted_url,
        )
        return False
    except Exception:
        logger.exception(
            "waitlist_email: send_exception provider=resend recipient=%s source=%s url=%s",
            recipient_email,
            source,
            redacted_url,
        )
        return False
