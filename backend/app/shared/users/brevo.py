"""Brevo transactional email client."""

from __future__ import annotations

import logging

import httpx

from app.shared.config import settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


async def send_email(*, to_email: str, subject: str, html: str, text: str | None = None) -> bool:
    """Send via Brevo. Returns False (and logs) if not configured or send fails."""
    if not settings.brevo_api_key or not settings.brevo_sender_email:
        logger.warning("Brevo not configured — skipping email to %s (%s)", to_email, subject)
        return False

    payload = {
        "sender": {
            "name": settings.brevo_sender_name or "Water Security Tool",
            "email": settings.brevo_sender_email,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
    }
    if text:
        payload["textContent"] = text

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                BREVO_SEND_URL,
                json=payload,
                headers={
                    "api-key": settings.brevo_api_key,
                    "accept": "application/json",
                    "content-type": "application/json",
                },
            )
        if resp.status_code >= 400:
            logger.error("Brevo send failed %s: %s", resp.status_code, resp.text[:400])
            return False
        logger.info(
            "Brevo accepted email to %s (%s) messageId=%s",
            to_email,
            subject,
            (resp.json() or {}).get("messageId"),
        )
        return True
    except httpx.HTTPError as exc:
        logger.error("Brevo request error: %s", exc)
        return False


async def send_verification_email(to_email: str, token: str) -> None:
    link = f"{settings.frontend_origin.rstrip('/')}/verify?token={token}"
    await send_email(
        to_email=to_email,
        subject="Verify your email — Water Security Tool",
        html=(
            f"<p>Welcome. Please verify your email to sign in.</p>"
            f'<p><a href="{link}">Verify email</a></p>'
            f"<p>Or paste this link: {link}</p>"
        ),
        text=f"Verify your email: {link}",
    )


async def send_reset_password_email(to_email: str, token: str) -> None:
    link = f"{settings.frontend_origin.rstrip('/')}/reset-password?token={token}"
    await send_email(
        to_email=to_email,
        subject="Reset your password — Water Security Tool",
        html=(
            f"<p>We received a password reset request.</p>"
            f'<p><a href="{link}">Reset password</a></p>'
            f"<p>Or paste this link: {link}</p>"
        ),
        text=f"Reset your password: {link}",
    )


async def send_welcome_email(to_email: str, name: str) -> None:
    await send_email(
        to_email=to_email,
        subject="Welcome to Water Security Tool",
        html=f"<p>Hi {name or 'there'},</p><p>Your account is ready. You can sign in and start diagnosing watersheds.</p>",
        text=f"Hi {name or 'there'}, your account is ready.",
    )
