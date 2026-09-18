"""SSE keepalive helper — prevents Cloudflare idle disconnects."""

from __future__ import annotations

import asyncio

import pytest

from app.modules.diagnose.services.sse_stream import iter_sse_with_keepalive


@pytest.mark.asyncio
async def test_sse_keepalive_emits_comment_while_waiting():
    queue: asyncio.Queue = asyncio.Queue()

    async def run():
        await asyncio.sleep(0.35)
        await queue.put({"type": "done", "percent": 100, "result": {"ok": True}})

    chunks = []
    async for chunk in iter_sse_with_keepalive(queue, run, keepalive_s=0.1):
        chunks.append(chunk)

    assert any(c.startswith(": keepalive") for c in chunks)
    assert any('"type": "done"' in c for c in chunks)


@pytest.mark.asyncio
async def test_sse_error_when_task_exits_without_event():
    queue: asyncio.Queue = asyncio.Queue()

    async def run():
        return  # no queue event

    chunks = []
    async for chunk in iter_sse_with_keepalive(queue, run, keepalive_s=0.05):
        chunks.append(chunk)

    assert any('"type": "error"' in c for c in chunks)
