import logging
from typing import Any, Optional

import httpx

from app.shared.config import settings
from .auth import ODKAuthManager
from .exceptions import (
    ODKAPIError,
    ODKAuthFailed,
    ODKConnectionError,
)

logger = logging.getLogger(__name__)


class ODKClient:
    """Simple ODK Central client that handles authentication and 401 retry.

    Usage:
        client = ODKClient()
        await client.get("/v1/projects")
    """

    def __init__(self, auth_manager: Optional[ODKAuthManager] = None):
        self.auth = auth_manager or ODKAuthManager()

    def _build_url(self, path: str) -> str:
        base = settings.odk_base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    async def _request(self, method: str, path: str, retry: bool = True, **kwargs: Any) -> httpx.Response:
        url = self._build_url(path)

        try:
            token = await self.auth.get_token()
        except ODKAuthFailed:
            raise

        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("ODK request error: %s", exc)
            raise ODKConnectionError("Network error communicating with ODK Central") from exc

        if resp.status_code == 401 and retry:
            # Token may be expired; invalidate and retry once.
            await self.auth.invalidate()
            try:
                token = await self.auth.get_token()
            except ODKAuthFailed as exc:
                raise
            headers["Authorization"] = f"Bearer {token}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise ODKConnectionError("Network error communicating with ODK Central") from exc

            # If still unauthorized, raise auth failure
            if resp.status_code == 401:
                raise ODKAuthFailed("ODK authentication failed after retry")

        if resp.status_code >= 400:
            if resp.status_code == 404:
                raise ODKAPIError(resp.status_code, "Not found")
            raise ODKAPIError(resp.status_code, resp.text[:1000] if resp.content else resp.reason_phrase)

        return resp

    async def get(self, path: str, **kwargs: Any) -> Any:
        resp = await self._request("GET", path, **kwargs)
        # Caller can inspect resp if needed; provide parsed JSON where possible
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content

    async def post(self, path: str, json: Any | None = None, data: Any | None = None, **kwargs: Any) -> Any:
        resp = await self._request("POST", path, json=json, data=data, **kwargs)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content
