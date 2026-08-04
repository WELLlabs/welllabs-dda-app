from contextlib import contextmanager
from typing import Generator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.shared.config import settings

_pool: ConnectionPool | None = None


def init_pool(*, min_size: int = 2, max_size: int = 10) -> ConnectionPool:
    """Create the global connection pool. Called once at app startup."""
    global _pool
    if _pool is not None:
        return _pool
    _pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=min_size,
        max_size=max_size,
        # Drop dead connections after PostGIS/Docker idle resets (login 500s).
        check=ConnectionPool.check_connection,
        max_idle=300,
        max_lifetime=3600,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    return _pool


def close_pool() -> None:
    """Shut down the global connection pool. Called at app shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool() at startup.")
    return _pool


@contextmanager
def db_cursor() -> Generator:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
