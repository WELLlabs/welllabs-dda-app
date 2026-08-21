"""UserManager with Brevo email hooks and Google signup name setup."""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Any, Optional, cast

import httpx
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions, models

from app.shared.config import settings
from app.shared.users import brevo
from app.shared.users.db import User, get_user_db

logger = logging.getLogger(__name__)

# Set during Google OAuth callback (same request) so login redirect can send
# brand-new accounts to the name confirmation page.
oauth_needs_name_setup: ContextVar[bool] = ContextVar("oauth_needs_name_setup", default=False)

_GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


async def _google_display_name(access_token: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        if resp.status_code >= 400:
            return ""
        profile = cast(dict[str, Any], resp.json())
        return (profile.get("name") or profile.get("given_name") or "").strip()[:200]
    except httpx.HTTPError:
        return ""


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.auth_jwt_secret
    verification_token_secret = settings.auth_jwt_secret

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info("User registered id=%s email=%s verified=%s", user.id, user.email, user.is_verified)
        if user.is_verified:
            await brevo.send_welcome_email(user.email, user.name or "")
            return
        await self.request_verify(user, request)

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        logger.info("Verification requested for %s", user.email)
        logger.debug("Verification token for %s: %s", user.email, token)
        await brevo.send_verification_email(user.email, token)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        logger.info("Password reset requested for %s", user.email)
        logger.debug("Reset token for %s: %s", user.email, token)
        await brevo.send_reset_password_email(user.email, token)

    async def on_after_verify(self, user: User, request: Optional[Request] = None):
        logger.info("User verified %s", user.email)
        await brevo.send_welcome_email(user.email, user.name or "")

    async def oauth_callback(
        self: "UserManager",
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> models.UOAP:
        is_new_user = False
        try:
            await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            try:
                await self.get_by_email(account_email)
            except exceptions.UserNotExists:
                is_new_user = True

        user = await super().oauth_callback(
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
            request=request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )

        if is_new_user:
            suggest = ""
            if oauth_name == "google" and access_token:
                suggest = await _google_display_name(access_token)
            if suggest:
                user = await self.user_db.update(user, {"name": suggest})
            oauth_needs_name_setup.set(True)
            logger.info("New OAuth user %s — name setup required (suggest=%r)", user.email, suggest)

        return user


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)
