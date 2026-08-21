import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from app.shared.config import settings
from .exceptions import ODKAuthFailed, ODKConnectionError

logger = logging.getLogger(__name__)


def _parse_expiry(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        # Try ISO format
        dt = datetime.fromisoformat(value)
        return dt.timestamp()
    except Exception:
        return None


class ODKAuthManager:
    """Manage a single backend-level ODK Central session token.

    This class caches a token and refreshes it when expired. It is safe
    for concurrent use within the same process.
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _login(self) -> None:
        url_base = settings.odk_base_url.rstrip("/")
        if not url_base or not settings.odk_username or not settings.odk_password:
            raise ODKAuthFailed("ODK_BASE_URL, ODK_USERNAME or ODK_PASSWORD not configured")

        login_url = f"{url_base}/v1/sessions"
        payload = {"email": settings.odk_username, "password": settings.odk_password}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(login_url, json=payload)
        except httpx.HTTPError as exc:
            logger.error("ODK login request failed: %s", exc)
            raise ODKConnectionError("Could not reach ODK Central") from exc

        if resp.status_code in (401, 403):
            raise ODKAuthFailed("Invalid ODK credentials")

        if resp.status_code not in (200, 201):
            text = resp.text if resp.content else resp.reason_phrase
            raise ODKAuthFailed(f"ODK login failed: {resp.status_code} {text}")

        data = resp.json()

        # Flexible token extraction to support a few possible response shapes.
        token = (
            data.get("token")
            or (data.get("api_key") or {}).get("token")
            or (data.get("session") or {}).get("token")
        )
        expires = (
            data.get("expires_at")
            or data.get("expiresAt")
            or (data.get("api_key") or {}).get("expiresAt")
        )

        if not token:
            raise ODKAuthFailed("ODK did not return an authentication token")

        expires_ts = _parse_expiry(expires)
        if not expires_ts:
            # Fall back to 24 hours if ODK didn't return expiry info
            expires_ts = time.time() + 24 * 3600

        self._token = token
        self._expires_at = expires_ts
        logger.info("Obtained ODK token; expires at %s", datetime.fromtimestamp(expires_ts).isoformat())

    async def get_token(self) -> str:
        now = time.time()
        # If token exists and is valid for at least another 60 seconds, reuse it.
        if self._token and now < self._expires_at - 60:
            return self._token

        # Otherwise, acquire lock and (re)login
        async with self._lock:
            # Another coroutine may have refreshed the token while we waited.
            now = time.time()
            if self._token and now < self._expires_at - 60:
                return self._token
            await self._login()
            if not self._token:
                raise ODKAuthFailed("Failed to obtain ODK token")
            return self._token

    async def invalidate(self) -> None:
        """Invalidate the cached token so the next request forces a login."""
        async with self._lock:
            self._token = None
            self._expires_at = 0.0
