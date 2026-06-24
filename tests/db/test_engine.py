import os
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine


def test_get_db_url_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Re-import after env change
    import importlib
    import app.db.engine as eng
    importlib.reload(eng)
    url = eng.get_db_url()
    assert url.startswith("sqlite+aiosqlite://")


def test_get_db_url_uses_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@host/db")
    import importlib
    import app.db.engine as eng
    importlib.reload(eng)
    url = eng.get_db_url()
    assert url.startswith("postgresql+asyncpg://")


async def test_get_async_engine_returns_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    import importlib
    import app.db.engine as eng
    importlib.reload(eng)
    engine = eng.get_async_engine()
    assert isinstance(engine, AsyncEngine)
