import httpx
from loguru import logger
from supabase import AsyncClient, AsyncClientOptions, acreate_client

from app.config import settings

# Every DB call runs on the bot's event loop. With the library default
# (120s per phase) a paused/dead Supabase project stalls each request for
# minutes; fail fast instead so handlers and the recall job get an error.
DB_HTTP_TIMEOUT_SECONDS = 10.0

_client: AsyncClient | None = None


async def create_db_client(
    url: str,
    key: str,
    *,
    timeout: float = DB_HTTP_TIMEOUT_SECONDS,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncClient:
    """Build an async Supabase client whose HTTP calls are bounded by ``timeout``."""
    # Same flags PostgREST uses for its own default httpx client, minus the
    # 120s timeout. ``transport`` exists for offline tests.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        http2=True,
        transport=transport,
    )
    return await acreate_client(url, key, options=AsyncClientOptions(httpx_client=http_client))


async def init_supabase() -> AsyncClient:
    """Create the shared client once, from async startup."""
    global _client
    if _client is not None:
        return _client
    try:
        # Используем Service Role Key (обходит RLS) или fallback на обычный ключ
        api_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
        if settings.SUPABASE_SERVICE_ROLE_KEY:
            logger.info("Supabase client initialized with SERVICE_ROLE_KEY (RLS bypassed)")
        else:
            logger.warning("Supabase client initialized with regular key (RLS may block operations)")

        _client = await create_db_client(settings.SUPABASE_URL, api_key)
    except Exception:
        logger.exception("Failed to initialize Supabase client")
        raise
    return _client


async def close_supabase() -> None:
    global _client
    if _client is None:
        return
    client, _client = _client, None
    await client.options.httpx_client.aclose()


def get_supabase() -> AsyncClient:
    if _client is None:
        raise RuntimeError("Supabase client is not initialized; await init_supabase() at startup")
    return _client
