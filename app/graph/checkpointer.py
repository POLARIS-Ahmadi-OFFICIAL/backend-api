from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def _db_path() -> str:
    # Resolve <repo_root>/data/polaris.db regardless of where the process runs
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent  # app/graph/checkpointer.py → 3 levels up to backend-api/
    db = repo_root / "data" / "polaris.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return str(db)


def get_checkpointer() -> AsyncSqliteSaver:
    """Return an AsyncSqliteSaver bound to the project's SQLite DB."""
    return AsyncSqliteSaver.from_conn_string(_db_path())
