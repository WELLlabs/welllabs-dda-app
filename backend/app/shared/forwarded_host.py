"""ASGI middleware: apply X-Forwarded-Host from the Vite /api proxy.

Uvicorn's ProxyHeadersMiddleware only honors X-Forwarded-For / Proto, so without
this, OAuth redirect_uri stays on :8080 instead of :5173/:5174.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


class ForwardedHostMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = MutableHeaders(scope=scope)
            forwarded = headers.get("x-forwarded-host")
            if forwarded:
                host_port = forwarded.split(",")[0].strip()
                headers["host"] = host_port
                host, sep, port_s = host_port.partition(":")
                if sep and port_s.isdigit():
                    scope["server"] = (host, int(port_s))
                else:
                    scope["server"] = (host_port, 0)
        await self.app(scope, receive, send)
