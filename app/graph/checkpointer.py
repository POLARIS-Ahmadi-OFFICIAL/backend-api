from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Module-level singleton — set by the FastAPI lifespan before any request arrives
_checkpointer: Optional[AsyncSqliteSaver] = None
_conn: Optional[aiosqlite.Connection] = None


def _db_path() -> str:
    # Resolve <repo_root>/data/polaris.db regardless of where the process runs
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent  # app/graph/checkpointer.py → 3 levels up to backend-api/
    db = repo_root / "data" / "polaris.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return str(db)


async def init_checkpointer() -> AsyncSqliteSaver:
    """Open the aiosqlite connection and return an AsyncSqliteSaver.

    Call this once from the FastAPI lifespan. The returned saver stays live
    as long as the underlying connection is open.
    """
    global _checkpointer, _conn
    _conn = await aiosqlite.connect(_db_path())
    _checkpointer = AsyncSqliteSaver(_conn)
    await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the aiosqlite connection on app shutdown."""
    global _checkpointer, _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
        _checkpointer = None


def get_checkpointer() -> AsyncSqliteSaver:
    """Return the already-initialised checkpointer singleton.

    Raises RuntimeError if called before init_checkpointer().
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer has not been initialised. "
            "Ensure init_checkpointer() is awaited in the FastAPI lifespan."
        )
    return _checkpointer
