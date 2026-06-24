from __future__ import annotations

from typing import Union
from app.db.engine import get_db_url

_checkpointer = None
_conn = None


async def init_checkpointer():
    """Open the appropriate checkpointer based on DATABASE_URL."""
    global _checkpointer, _conn
    url = get_db_url()
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        import psycopg
        # psycopg3 connection string: replace asyncpg scheme
        pg_url = url.replace("postgresql+asyncpg://", "postgresql://")
        _conn = await psycopg.AsyncConnection.connect(pg_url)
        _checkpointer = AsyncPostgresSaver(_conn)
        await _checkpointer.setup()
    else:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from pathlib import Path
        db_path = url.replace("sqlite+aiosqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _conn = await aiosqlite.connect(db_path)
        _checkpointer = AsyncSqliteSaver(_conn)
        await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
        _checkpointer = None


def get_checkpointer():
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer has not been initialised. "
            "Ensure init_checkpointer() is awaited in the FastAPI lifespan."
        )
    return _checkpointer
