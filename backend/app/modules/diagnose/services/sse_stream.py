"""SSE helpers for long-running diagnose operations behind Cloudflare."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

# Cloudflare proxies idle HTTP connections ~100s. Keepalives must be more frequent.
_SSE_KEEPALIVE_S = 15.0


async def iter_sse_with_keepalive(
    queue: asyncio.Queue,
    run: Callable[[], Awaitable[None]],
    *,
    keepalive_s: float = _SSE_KEEPALIVE_S,
) -> AsyncIterator[str]:
    """Yield SSE `data:` events from *queue*, plus comment keepalives while waiting.

    *run* is scheduled as a task and should push ``done`` / ``error`` (and optional
    ``progress``) dicts onto *queue*. Client ``streamSSE`` ignores comment lines.
    """
    task = asyncio.create_task(run())
    try:
        while True:
            try:
                item: dict[str, Any] = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
            except asyncio.TimeoutError:
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                    else:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "error",
                                    "message": "Export finished without a completion event",
                                }
                            )
                            + "\n\n"
                        )
                    break
                # SSE comment — keeps Cloudflare / nginx from closing idle streams
                yield ": keepalive\n\n"
                continue

            yield f"data: {json.dumps(item)}\n\n"
            if item.get("type") in ("done", "error"):
                break
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            await task
