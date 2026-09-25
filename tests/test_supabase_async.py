"""The DB client must never freeze the bot's event loop (offline tests).

Incident: the sync Supabase client ran blocking httpx calls on the aiogram
loop. When the project paused, each call hung ~2 minutes and getUpdates
never ran. These tests pin both halves of the fix: DB calls yield the loop,
and a stalled DB fails within a timeout of seconds.
"""
import asyncio
import os
import time

import httpx
import pytest

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from supabase import ClientOptions, create_client  # noqa: E402

import app.infrastructure.supabase.client as supabase_client  # noqa: E402
from app.infrastructure.supabase.client import (  # noqa: E402
    DB_HTTP_TIMEOUT_SECONDS,
    close_supabase,
    create_db_client,
    get_supabase,
    init_supabase,
)

DB_URL = "http://db.test"
STALL_SECONDS = 0.5
TICK_SECONDS = 0.01


async def _ticks_while(query) -> int:
    """Run ``query`` next to a ticker; return how often the ticker ran meanwhile."""
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            ticks += 1
            await asyncio.sleep(TICK_SECONDS)

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0)  # let the ticker start
    ticks = 0
    try:
        await query()
    finally:
        done.set()
        await task
    return ticks


def test_stalled_async_db_call_keeps_the_event_loop_alive():
    async def stalled_db(_request):
        await asyncio.sleep(STALL_SECONDS)
        return httpx.Response(200, json=[])

    async def run():
        client = await create_db_client(DB_URL, "test-key", transport=httpx.MockTransport(stalled_db))
        try:
            async def query():
                await client.table("users").select("*").execute()
            return await _ticks_while(query)
        finally:
            await client.options.httpx_client.aclose()

    ticks = asyncio.run(run())

    # ~50 ticks fit in the stall; demand a clear majority, not an exact count.
    assert ticks >= (STALL_SECONDS / TICK_SECONDS) * 0.5


def test_stalled_sync_db_call_freezes_the_event_loop():
    """The same scenario with the old sync client: the ticker never runs.

    This is the incident reproduced; it is what the liveness test above
    would observe (0 ticks -> failure) if the sync client came back.
    """
    def stalled_db(_request):
        time.sleep(STALL_SECONDS)
        return httpx.Response(200, json=[])

    sync_client = create_client(
        DB_URL,
        "test-key",
        options=ClientOptions(httpx_client=httpx.Client(transport=httpx.MockTransport(stalled_db))),
    )

    async def query():
        sync_client.table("users").select("*").execute()

    ticks = asyncio.run(_ticks_while(query))

    assert ticks == 0


@pytest.fixture
def blackhole_server():
    """A local TCP server that accepts connections and never answers."""
    loop = asyncio.new_event_loop()

    async def hold(reader, _writer):
        await reader.read()  # wait until the client gives up

    server = loop.run_until_complete(asyncio.start_server(hold, "127.0.0.1", 0))
    port = server.sockets[0].getsockname()[1]
    yield loop, f"http://127.0.0.1:{port}"
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


def test_stalled_db_call_times_out_within_configured_timeout(blackhole_server, monkeypatch):
    # httpx enforces timeouts in the network layer, so this needs a real
    # socket that stalls; a mock transport cannot exercise it.
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    loop, url = blackhole_server
    timeout = 0.3

    async def run():
        client = await create_db_client(url, "test-key", timeout=timeout)
        started = loop.time()
        try:
            with pytest.raises(httpx.TimeoutException):
                await client.table("users").select("*").execute()
        finally:
            await client.options.httpx_client.aclose()
        return loop.time() - started

    elapsed = loop.run_until_complete(run())

    assert timeout * 0.9 <= elapsed < timeout + 1


def test_default_db_timeout_is_seconds_not_minutes():
    async def run():
        client = await create_db_client(DB_URL, "test-key")
        try:
            return client.options.httpx_client.timeout
        finally:
            await client.options.httpx_client.aclose()

    timeout = asyncio.run(run())

    assert DB_HTTP_TIMEOUT_SECONDS <= 30
    assert timeout == httpx.Timeout(DB_HTTP_TIMEOUT_SECONDS)


def test_shared_client_is_created_once_at_startup(monkeypatch):
    monkeypatch.setattr(supabase_client, "_client", None)
    with pytest.raises(RuntimeError):
        get_supabase()

    async def run():
        first = await init_supabase()
        second = await init_supabase()
        shared = get_supabase()
        await close_supabase()
        return first, second, shared

    first, second, shared = asyncio.run(run())

    assert first is second is shared
    with pytest.raises(RuntimeError):
        get_supabase()
