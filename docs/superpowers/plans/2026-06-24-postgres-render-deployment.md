# Postgres Migration & Render Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw `sqlite3` DatabaseManager with SQLAlchemy Core async (dual-driver: asyncpg for Postgres, aiosqlite for SQLite), deploy the backend on Render, and wire Vercel + mobile to the public URL.

**Architecture:** `DATABASE_URL` env var selects the driver — `postgresql+asyncpg://` for Render/production, `sqlite+aiosqlite:///` for local dev and desktop. DatabaseManager keeps its exact public API (`get`/`set`/`append_conversation_event` etc.) so all callers above it are unchanged. LangGraph checkpointer switches from `AsyncSqliteSaver` to `AsyncPostgresSaver` when Postgres is detected.

**Tech Stack:** SQLAlchemy 2.0 async Core, asyncpg, aiosqlite, psycopg3, langgraph-checkpoint-postgres, Render (Docker Web Service + managed Postgres), render.yaml

## Global Constraints

- Python `>=3.12` (pyproject.toml floor)
- SQLAlchemy `>=2.0.36` already in pyproject.toml — use `sqlalchemy[asyncio]` extras
- `psycopg[binary]>=3.2.0` already in pyproject.toml — also add `psycopg[pool]` extra
- `DATABASE_URL` unset → default `sqlite+aiosqlite:///./data/polaris.db`
- `DATABASE_URL` starting with `postgresql` → use asyncpg + Alembic migrations
- DatabaseManager public API must stay byte-for-byte identical: `get(key, default)`, `set(key, value)`, `clear_conversation_events`, `get_conversation_events`, `append_conversation_event`, `get_workflows`, `save_workflow`, `delete_workflow`, `get_workflow_steps`, `get_uploaded_files`, `add_uploaded_file`, `clear_session_state`, `clear_all_except`, `create_user`, `get_user`, `list_users`, `create_experiment`, `list_experiments`, `get_experiment`, `set_current_experiment`, `load_experiment_into_session`, `add_negative_hypothesis`, `get_negative_hypotheses`, `add_hypothesis_outcome`, `get_hypothesis_outcomes`
- All 14 tables must exist in both SQLite and Postgres schemas with identical column names
- `init_db.py` must run correctly in Docker startup (no interactive input, no Streamlit)
- `start.sh` replaces `railway-start.sh` — Dockerfile must reference `start.sh`
- Existing 36 passing tests must continue to pass
- `render.yaml` uses `plan: free` for the database

---

## Task 1: Add dependencies and async engine factory

**Files:**
- Modify: `pyproject.toml`
- Create: `app/db/engine.py`
- Create: `tests/db/__init__.py`
- Create: `tests/db/test_engine.py`

**Interfaces:**
- Produces:
  - `get_async_engine() -> AsyncEngine` — returns a module-level singleton AsyncEngine based on `DATABASE_URL`
  - `get_db_url() -> str` — returns the resolved DATABASE_URL (exported for use in checkpointer and init_db)

- [ ] **Step 1: Add dependencies to pyproject.toml**

Open `pyproject.toml`. In the `dependencies` list, make these changes:
- Change `"sqlalchemy>=2.0.36"` → `"sqlalchemy[asyncio]>=2.0.36"`
- Change `"psycopg[binary]>=3.2.0"` → `"psycopg[binary,pool]>=3.2.0"`
- Add after `"langgraph-checkpoint-sqlite>=1.0.0"`:
  - `"langgraph-checkpoint-postgres>=2.0.0"`
  - `"asyncpg>=0.29.0"`

The final dependencies block around these lines should look like:
```toml
  "sqlalchemy[asyncio]>=2.0.36",
  "alembic>=1.14.0",
  "psycopg[binary,pool]>=3.2.0",
  "asyncpg>=0.29.0",
  ...
  "langgraph-checkpoint-sqlite>=1.0.0",
  "langgraph-checkpoint-postgres>=2.0.0",
```

- [ ] **Step 2: Install updated dependencies**

```bash
cd backend-api
pip install -e ".[dev]"
```

Expected: successful install with `asyncpg` and `langgraph-checkpoint-postgres` listed.

- [ ] **Step 3: Create `app/db/` package**

```bash
mkdir -p app/db
touch app/db/__init__.py
```

- [ ] **Step 4: Write the failing test**

Create `tests/db/__init__.py` (empty) and `tests/db/test_engine.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
python3 -m pytest tests/db/test_engine.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `app.db.engine`.

- [ ] **Step 6: Implement `app/db/engine.py`**

```python
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_DEFAULT_URL = "sqlite+aiosqlite:///./data/polaris.db"
_engine: AsyncEngine | None = None


def get_db_url() -> str:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgresql+asyncpg://") or raw.startswith("sqlite+aiosqlite://"):
        return raw
    if raw.startswith("sqlite://"):
        return raw.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return _DEFAULT_URL


def get_async_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_db_url()
        if url.startswith("sqlite"):
            _engine = create_async_engine(url, connect_args={"check_same_thread": False})
        else:
            _engine = create_async_engine(url, pool_size=5, max_overflow=10)
    return _engine
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
python3 -m pytest tests/db/test_engine.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add app/db/__init__.py app/db/engine.py tests/db/__init__.py tests/db/test_engine.py pyproject.toml
git commit -m "feat(db): add async engine factory with SQLite/Postgres dual-driver support"
```

---

## Task 2: Rewrite DatabaseManager with SQLAlchemy async

**Files:**
- Modify: `app/tools/database.py` (full rewrite — keep exact same public API)
- Create: `tests/db/test_database_manager.py`

**Interfaces:**
- Consumes: `get_async_engine() -> AsyncEngine` from `app.db.engine`
- Produces: `DatabaseManager` class with the same 25 public methods listed in Global Constraints

**Note on architecture:** The existing `DatabaseManager` is synchronous. The rewrite uses `asyncio.get_event_loop().run_until_complete()` (or a sync wrapper via `asyncio.run()`) to keep the public API synchronous — this preserves all callers. Internally, each method opens an `AsyncConnection` via `async with engine.begin() as conn:` and uses `await conn.execute(text(...))`. A thin `_run(coro)` helper bridges sync→async.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_database_manager.py`:

```python
import pytest
import os


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    import importlib
    import app.db.engine as eng
    importlib.reload(eng)
    eng._engine = None  # reset singleton
    import app.tools.database as dbmod
    importlib.reload(dbmod)
    manager = dbmod.DatabaseManager()
    manager.init_schema()
    manager.ensure_defaults()
    return manager


def test_get_returns_default_for_unknown_key(db):
    assert db.get("nonexistent_key", "fallback") == "fallback"


def test_set_and_get_app_config_string(db):
    db.set("api_key", "test-key-123")
    assert db.get("api_key") == "test-key-123"


def test_set_and_get_app_config_bool(db):
    db.set("experimental_mode", True)
    assert db.get("experimental_mode") is True


def test_set_and_get_app_config_int(db):
    db.set("current_experiment_id", 42)
    assert db.get("current_experiment_id") == 42


def test_set_and_get_json(db):
    db.set("experimental_constraints", {"techniques": ["NMR"], "equipment": [], "parameters": [], "focus_areas": [], "liquid_handling": {}})
    result = db.get("experimental_constraints")
    assert result["techniques"] == ["NMR"]


def test_append_and_get_conversation_events(db):
    db.append_conversation_event("test_event", "graph", "session-1", {"key": "val"})
    events = db.get_conversation_events()
    assert len(events) == 1
    assert events[0]["type"] == "test_event"
    assert events[0]["payload"]["key"] == "val"


def test_create_and_get_user(db):
    db.create_user("user-1", "Alice")
    user = db.get_user("user-1")
    assert user["name"] == "Alice"


def test_create_experiment_and_list(db):
    db.create_user("user-1", "Alice")
    exp_id = db.create_experiment("user-1", "My Experiment")
    experiments = db.list_experiments("user-1")
    assert len(experiments) == 1
    assert experiments[0]["name"] == "My Experiment"
    assert experiments[0]["id"] == exp_id


def test_save_and_get_workflow(db):
    db.save_workflow("wf1", [{"name": "Hypothesis Agent", "automatic": False}])
    wfs = db.get_workflows()
    assert "wf1" in wfs
    assert wfs["wf1"]["steps"][0]["name"] == "Hypothesis Agent"


def test_add_and_get_uploaded_file(db):
    db.add_uploaded_file("data.csv", "/tmp/data.csv")
    files = db.get_uploaded_files()
    assert len(files) == 1
    assert files[0]["name"] == "data.csv"


def test_add_and_get_negative_hypothesis(db):
    db.add_negative_hypothesis("H1", "rejected", research_question="Q?", analysis_summary="summary")
    results = db.get_negative_hypotheses()
    assert len(results) == 1
    assert results[0]["hypothesis_text"] == "H1"


def test_add_and_get_hypothesis_outcome(db):
    db.add_hypothesis_outcome("H2", "confirmed", material_hint="NMR", evidence_summary="strong")
    results = db.get_hypothesis_outcomes()
    assert len(results) == 1
    assert results[0]["status"] == "confirmed"


def test_experiment_scoped_set_get(db):
    db.create_user("user-1", "Alice")
    exp_id = db.create_experiment("user-1", "Exp")
    db.set("current_experiment_id", exp_id)
    db.set("research_goal", "test goal")
    assert db.get("research_goal") == "test goal"


def test_clear_session_state(db):
    db.set("stage", "hypothesis")
    db.clear_session_state()
    # After clear, should return default or None
    result = db.get("stage")
    assert result is None or result == "initial"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/db/test_database_manager.py -v 2>&1 | head -30
```

Expected: all fail (old implementation uses sqlite3, tests reload with new env).

- [ ] **Step 3: Rewrite `app/tools/database.py`**

Replace the entire file with the SQLAlchemy async implementation. The key patterns:

```python
"""
SQLAlchemy async DatabaseManager — supports both SQLite (aiosqlite) and Postgres (asyncpg).
Public API is identical to the original sqlite3 implementation.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.engine import get_async_engine

# ── keep all the constants unchanged ──────────────────────────────────────────
EXPERIMENT_SCOPED_KEYS = frozenset([
    "stage", "last_hypothesis", "experimental_outputs", "analysis_results", "curve_fitting_results",
    "interactions", "hypothesis_ready", "stop_hypothesis", "hypothesis_round_count",
    "workflow_active", "workflow_step", "workflow_completed", "workflow_experiment_started",
    "workflow_experiment_completed", "workflow_experiment_outputs", "research_goal",
    "current_workflow", "workflow_steps", "conversation_history", "allow_followup",
    "selected_wells", "plate_format", "last_processed_trigger_time", "watcher_auto_triggered_file",
    "watcher_auto_trigger_time", "auto_triggered_results", "auto_triggered_results_file",
    "auto_run_curve_fitting", "auto_run_data_file", "auto_run_comp_file", "auto_run_params",
    "auto_ml_after_curve_fitting", "auto_route_to_analysis", "workflow_curve_fitting_files",
    "ml_auto_json_path", "ml_auto_csv_path", "ml_auto_composition_path",
    "manual_clarified_question", "manual_socratic_questions", "manual_socratic_answers",
    "manual_thoughts", "manual_hypothesis", "optimization_model_choice", "ml_model_config",
    "gp_results", "gp_results_available", "analysis_ready", "analysis_recommendations",
    "gp_suggested_compositions", "analysis_full_report", "analysis_feedback", "next_agent",
    "pending_additional_question", "workflow_ml_model_choice", "workflow_curve_fitting_completed",
    "workflow_created_at", "demo_workflow_running", "prompt_session", "current_prompt_session_id",
])

DEFAULT_APP_CONFIG = {
    "start_time": None,
    "api_key": "",
    "api_key_source": "",
    "current_user_id": "",
    "current_experiment_id": 0,
    "llm_provider": "qwen",
    "llm_model": "Qwen/Qwen2.5-VL-72B-Instruct",
    "qwen_base_url": "https://router.huggingface.co/v1",
    "stage": "initial",
    "cf_data_path": "",
    "cf_comp_path": "",
    "experimental_mode": False,
    "routing_mode": "Autonomous (LLM)",
    "max_hypothesis_rounds": 5,
    "experiment_memory_file": "experiment_memory.json",
    "experiment_data_dir": "data",
    "watcher_directory": "",
    "watcher_results_dir": "results",
    "watcher_enabled": False,
    "watcher_port": 8000,
}

DEFAULT_EXPERIMENTAL_CONSTRAINTS = {
    "techniques": [], "equipment": [], "parameters": [], "focus_areas": [],
    "liquid_handling": {"max_volume_per_mixture": 50, "instruments": [], "plate_format": "96-well", "materials": [], "csv_path": "/var/lib/jupyter/notebooks/Dual GP 5AVA BDA/"},
}

DEFAULT_JUPYTER_CONFIG = {
    "server_url": "http://10.140.141.160:48888/", "token": "", "upload_enabled": False, "notebook_path": "Automated Agent",
}

DEFAULT_SESSION_STATE = {
    "conversation_events": [], "current_prompt_session_id": None,
    "manual_workflow": ["Hypothesis Agent", "Experiment Agent", "Curve Fitting"],
    "workflow_index": 0, "workflow_auto_flags": {}, "current_workflow_name": None,
    "uploaded_files": [], "hypothesis_ready": False, "last_hypothesis": None,
    "experimental_outputs": None, "stop_hypothesis": False, "hypothesis_round_count": 0,
    "workflow_active": False, "workflow_step": "idle", "workflow_completed": False,
    "workflow_experiment_started": False, "workflow_experiment_completed": False,
    "workflow_experiment_outputs": None, "research_goal": "",
}

DEFAULT_AGENT_COUNTS = {
    "hypothesis": 0, "experiment": 0, "curve_fit": 0, "analysis": 0, "router": 0, "watcher": 0,
}


def _run(coro):
    """Run an async coroutine synchronously from sync callers."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context (e.g. FastAPI request) — use a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _is_postgres(engine: AsyncEngine) -> bool:
    return str(engine.url).startswith("postgresql")


def _upsert_sql(table: str, pk_col: str, pk_val, columns: dict, engine: AsyncEngine) -> tuple:
    """Build upsert SQL compatible with both SQLite and Postgres."""
    cols = list(columns.keys())
    all_cols = [pk_col] + cols
    all_vals = [pk_val] + [columns[c] for c in cols]
    placeholders = ", ".join(f":{c}" for c in all_cols)
    params = dict(zip(all_cols, all_vals))
    params[pk_col] = pk_val

    if _is_postgres(engine):
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(all_cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk_col}) DO UPDATE SET {update_set}"
        )
    else:
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(all_cols)}) VALUES ({placeholders})"
    return sql, params


class DatabaseManager:
    """SQLAlchemy async persistence — SQLite (aiosqlite) or Postgres (asyncpg)."""

    def __init__(self, engine: Optional[AsyncEngine] = None):
        self._engine = engine or get_async_engine()

    # ── schema ────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        _run(self._init_schema_async())

    async def _init_schema_async(self) -> None:
        pg = _is_postgres(self._engine)
        serial = "BIGSERIAL" if pg else "INTEGER"
        autoincrement = "" if pg else "AUTOINCREMENT"
        check_pk1 = "PRIMARY KEY" if pg else "INTEGER PRIMARY KEY CHECK (id = 1)"
        pk1_col = "id BIGINT PRIMARY KEY DEFAULT 1 CHECK (id = 1)" if pg else "id INTEGER PRIMARY KEY CHECK (id = 1)"
        now_fn = "NOW()" if pg else "CURRENT_TIMESTAMP"

        ddl_statements = [
            f"""CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value_text TEXT,
                value_int BIGINT,
                value_real DOUBLE PRECISION,
                value_json TEXT
            )""",
            f"""CREATE TABLE IF NOT EXISTS experimental_constraints (
                {pk1_col},
                techniques_json TEXT,
                equipment_json TEXT,
                parameters_json TEXT,
                focus_areas_json TEXT,
                liquid_handling_json TEXT
            )""",
            f"""CREATE TABLE IF NOT EXISTS jupyter_config (
                {pk1_col},
                server_url TEXT,
                token TEXT,
                upload_enabled INTEGER,
                notebook_path TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS experiments (
                id {serial} PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )""",
            """CREATE TABLE IF NOT EXISTS experiment_data (
                experiment_id BIGINT PRIMARY KEY,
                state_json TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            )""",
            f"""CREATE TABLE IF NOT EXISTS conversation_events (
                id {serial} PRIMARY KEY {'DEFAULT' if pg else 'AUTOINCREMENT'[0:0]},
                experiment_id BIGINT,
                type TEXT NOT NULL,
                mode TEXT NOT NULL,
                prompt_session_id TEXT,
                timestamp TEXT NOT NULL,
                payload_json TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            )""",
            """CREATE TABLE IF NOT EXISTS agent_usage_counts (
                agent_name TEXT PRIMARY KEY,
                count BIGINT NOT NULL DEFAULT 0
            )""",
            f"""CREATE TABLE IF NOT EXISTS workflows (
                id {serial} PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT,
                ml_model_choice TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS workflow_steps (
                workflow_id BIGINT NOT NULL,
                step_order BIGINT NOT NULL,
                name TEXT NOT NULL,
                automatic INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (workflow_id, step_order),
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            )""",
            f"""CREATE TABLE IF NOT EXISTS uploaded_files (
                id {serial} PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS session_state (
                {pk1_col},
                state_json TEXT
            )""",
            f"""CREATE TABLE IF NOT EXISTS negative_hypotheses (
                id {serial} PRIMARY KEY,
                hypothesis_text TEXT NOT NULL,
                status TEXT NOT NULL,
                research_question TEXT,
                analysis_summary TEXT,
                context_json TEXT,
                created_at TEXT NOT NULL
            )""",
            f"""CREATE TABLE IF NOT EXISTS hypothesis_outcomes (
                id {serial} PRIMARY KEY,
                hypothesis_text TEXT NOT NULL,
                material_hint TEXT,
                status TEXT NOT NULL,
                evidence_summary TEXT,
                source TEXT,
                created_at TEXT NOT NULL
            )""",
        ]

        async with self._engine.begin() as conn:
            for stmt in ddl_statements:
                await conn.execute(text(stmt))

    def ensure_defaults(self) -> None:
        _run(self._ensure_defaults_async())

    async def _ensure_defaults_async(self) -> None:
        await self._init_schema_async()
        async with self._engine.begin() as conn:
            # app_config defaults
            for key, value in DEFAULT_APP_CONFIG.items():
                if value is None:
                    continue
                existing = (await conn.execute(
                    text("SELECT 1 FROM app_config WHERE key = :k"), {"k": key}
                )).fetchone()
                if existing is None:
                    await self._set_config_value_async(conn, key, value)

            # experimental_constraints
            if not (await conn.execute(text("SELECT 1 FROM experimental_constraints WHERE id = 1"))).fetchone():
                ec = DEFAULT_EXPERIMENTAL_CONSTRAINTS
                await conn.execute(text(
                    "INSERT INTO experimental_constraints (id, techniques_json, equipment_json, parameters_json, focus_areas_json, liquid_handling_json) "
                    "VALUES (1, :t, :e, :p, :f, :l)"
                ), {"t": json.dumps(ec["techniques"]), "e": json.dumps(ec["equipment"]),
                    "p": json.dumps(ec["parameters"]), "f": json.dumps(ec["focus_areas"]),
                    "l": json.dumps(ec["liquid_handling"])})

            # jupyter_config
            if not (await conn.execute(text("SELECT 1 FROM jupyter_config WHERE id = 1"))).fetchone():
                jc = DEFAULT_JUPYTER_CONFIG
                await conn.execute(text(
                    "INSERT INTO jupyter_config (id, server_url, token, upload_enabled, notebook_path) VALUES (1, :s, :t, :u, :n)"
                ), {"s": jc["server_url"], "t": jc["token"], "u": int(jc["upload_enabled"]), "n": jc["notebook_path"]})

            # agent_usage_counts
            for agent, count in DEFAULT_AGENT_COUNTS.items():
                if not (await conn.execute(text("SELECT 1 FROM agent_usage_counts WHERE agent_name = :a"), {"a": agent})).fetchone():
                    await conn.execute(text("INSERT INTO agent_usage_counts (agent_name, count) VALUES (:a, :c)"), {"a": agent, "c": count})

            # session_state
            if not (await conn.execute(text("SELECT 1 FROM session_state WHERE id = 1"))).fetchone():
                state = dict(DEFAULT_SESSION_STATE)
                state["current_prompt_session_id"] = str(uuid.uuid4())
                state["start_time"] = datetime.now().timestamp()
                await conn.execute(text("INSERT INTO session_state (id, state_json) VALUES (1, :s)"), {"s": json.dumps(state)})

    async def _set_config_value_async(self, conn, key: str, value: Any) -> None:
        pg = _is_postgres(self._engine)
        upsert = "INSERT INTO app_config (key, {col}) VALUES (:k, :v) ON CONFLICT (key) DO UPDATE SET {col} = EXCLUDED.{col}" if pg else "INSERT OR REPLACE INTO app_config (key, {col}) VALUES (:k, :v)"
        if isinstance(value, bool):
            await conn.execute(text(upsert.format(col="value_int")), {"k": key, "v": 1 if value else 0})
        elif isinstance(value, int):
            await conn.execute(text(upsert.format(col="value_int")), {"k": key, "v": value})
        elif isinstance(value, float):
            await conn.execute(text(upsert.format(col="value_real")), {"k": key, "v": value})
        elif isinstance(value, (dict, list)):
            await conn.execute(text(upsert.format(col="value_json")), {"k": key, "v": json.dumps(value)})
        else:
            await conn.execute(text(upsert.format(col="value_text")), {"k": key, "v": str(value) if value is not None else ""})

    # ── get ───────────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return _run(self._get_async(key, default))

    async def _get_async(self, key: str, default: Any = None) -> Any:
        async with self._engine.connect() as conn:
            if key in DEFAULT_APP_CONFIG:
                row = (await conn.execute(
                    text("SELECT value_text, value_int, value_real, value_json FROM app_config WHERE key = :k"),
                    {"k": key}
                )).fetchone()
                if row is None:
                    return DEFAULT_APP_CONFIG.get(key, default)
                for i, col in enumerate(["value_text", "value_int", "value_real", "value_json"]):
                    v = row[i]
                    if v is not None:
                        if col == "value_json":
                            try:
                                return json.loads(v)
                            except json.JSONDecodeError:
                                return v
                        if col == "value_int" and key == "experimental_mode":
                            return bool(v)
                        return v
                return default

            if key == "experimental_constraints":
                row = (await conn.execute(text(
                    "SELECT techniques_json, equipment_json, parameters_json, focus_areas_json, liquid_handling_json FROM experimental_constraints WHERE id = 1"
                ))).fetchone()
                if row is None:
                    return DEFAULT_EXPERIMENTAL_CONSTRAINTS
                return {
                    "techniques": json.loads(row[0] or "[]"),
                    "equipment": json.loads(row[1] or "[]"),
                    "parameters": json.loads(row[2] or "[]"),
                    "focus_areas": json.loads(row[3] or "[]"),
                    "liquid_handling": json.loads(row[4] or "{}"),
                }

            if key == "jupyter_config":
                row = (await conn.execute(text(
                    "SELECT server_url, token, upload_enabled, notebook_path FROM jupyter_config WHERE id = 1"
                ))).fetchone()
                if row is None:
                    return DEFAULT_JUPYTER_CONFIG
                return {"server_url": row[0] or "", "token": row[1] or "", "upload_enabled": bool(row[2]) if row[2] is not None else False, "notebook_path": row[3] or "Automated Agent"}

            if key == "workflows":
                return await self._get_workflows_async(conn)

            if key == "conversation_events":
                return await self._get_conversation_events_async(conn)

            if key == "uploaded_files":
                return await self._get_uploaded_files_async(conn)

            if key == "agent_usage_counts":
                rows = (await conn.execute(text("SELECT agent_name, count FROM agent_usage_counts"))).fetchall()
                return {r[0]: r[1] for r in rows} if rows else dict(DEFAULT_AGENT_COUNTS)

            if key in EXPERIMENT_SCOPED_KEYS:
                exp_id_row = (await conn.execute(
                    text("SELECT value_int FROM app_config WHERE key = 'current_experiment_id'")
                )).fetchone()
                exp_id = int(exp_id_row[0]) if exp_id_row and exp_id_row[0] else 0
                if exp_id > 0:
                    row = (await conn.execute(
                        text("SELECT state_json FROM experiment_data WHERE experiment_id = :id"),
                        {"id": exp_id}
                    )).fetchone()
                    if row:
                        state = json.loads(row[0] or "{}")
                        if key in state:
                            val = state[key]
                            return set(val) if key == "selected_wells" and isinstance(val, list) else val
                row = (await conn.execute(text("SELECT state_json FROM session_state WHERE id = 1"))).fetchone()
                if row is None:
                    return default
                state = json.loads(row[0] or "{}")
                if key in state:
                    val = state[key]
                    return set(val) if key == "selected_wells" and isinstance(val, list) else val
                return default

            return default

    # ── set ───────────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        _run(self._set_async(key, value))

    async def _set_async(self, key: str, value: Any) -> None:
        pg = _is_postgres(self._engine)
        async with self._engine.begin() as conn:
            if key in DEFAULT_APP_CONFIG:
                await self._set_config_value_async(conn, key, value)
                return

            if key == "experimental_constraints":
                ec = value
                upsert = (
                    "INSERT INTO experimental_constraints (id, techniques_json, equipment_json, parameters_json, focus_areas_json, liquid_handling_json) "
                    "VALUES (1, :t, :e, :p, :f, :l) ON CONFLICT (id) DO UPDATE SET "
                    "techniques_json=EXCLUDED.techniques_json, equipment_json=EXCLUDED.equipment_json, "
                    "parameters_json=EXCLUDED.parameters_json, focus_areas_json=EXCLUDED.focus_areas_json, "
                    "liquid_handling_json=EXCLUDED.liquid_handling_json"
                ) if pg else (
                    "INSERT OR REPLACE INTO experimental_constraints (id, techniques_json, equipment_json, parameters_json, focus_areas_json, liquid_handling_json) "
                    "VALUES (1, :t, :e, :p, :f, :l)"
                )
                await conn.execute(text(upsert), {
                    "t": json.dumps(ec.get("techniques", [])), "e": json.dumps(ec.get("equipment", [])),
                    "p": json.dumps(ec.get("parameters", [])), "f": json.dumps(ec.get("focus_areas", [])),
                    "l": json.dumps(ec.get("liquid_handling", {}))
                })
                return

            if key == "jupyter_config":
                jc = value
                upsert = (
                    "INSERT INTO jupyter_config (id, server_url, token, upload_enabled, notebook_path) "
                    "VALUES (1, :s, :t, :u, :n) ON CONFLICT (id) DO UPDATE SET "
                    "server_url=EXCLUDED.server_url, token=EXCLUDED.token, upload_enabled=EXCLUDED.upload_enabled, notebook_path=EXCLUDED.notebook_path"
                ) if pg else (
                    "INSERT OR REPLACE INTO jupyter_config (id, server_url, token, upload_enabled, notebook_path) VALUES (1, :s, :t, :u, :n)"
                )
                await conn.execute(text(upsert), {
                    "s": jc.get("server_url", ""), "t": jc.get("token", ""),
                    "u": int(jc.get("upload_enabled", False)), "n": jc.get("notebook_path", "Automated Agent")
                })
                return

            if key == "agent_usage_counts":
                for agent, count in value.items():
                    upsert = (
                        "INSERT INTO agent_usage_counts (agent_name, count) VALUES (:a, :c) "
                        "ON CONFLICT (agent_name) DO UPDATE SET count=EXCLUDED.count"
                    ) if pg else "INSERT OR REPLACE INTO agent_usage_counts (agent_name, count) VALUES (:a, :c)"
                    await conn.execute(text(upsert), {"a": agent, "c": count})
                return

            if key == "workflows" and isinstance(value, dict):
                for wf_name, wf_data in value.items():
                    if isinstance(wf_data, dict):
                        await self._save_workflow_async(conn, wf_name, wf_data.get("steps", []), wf_data.get("ml_model_choice"), pg)
                return

            if key == "selected_wells" and isinstance(value, set):
                value = list(value)

            exp_id_row = (await conn.execute(
                text("SELECT value_int FROM app_config WHERE key = 'current_experiment_id'")
            )).fetchone()
            exp_id = int(exp_id_row[0]) if exp_id_row and exp_id_row[0] else 0

            if key in EXPERIMENT_SCOPED_KEYS and exp_id > 0:
                row = (await conn.execute(
                    text("SELECT state_json FROM experiment_data WHERE experiment_id = :id"), {"id": exp_id}
                )).fetchone()
                state = json.loads(row[0] or "{}") if row else {}
                state[key] = value
                upsert = (
                    "INSERT INTO experiment_data (experiment_id, state_json) VALUES (:id, :s) "
                    "ON CONFLICT (experiment_id) DO UPDATE SET state_json=EXCLUDED.state_json"
                ) if pg else "INSERT OR REPLACE INTO experiment_data (experiment_id, state_json) VALUES (:id, :s)"
                await conn.execute(text(upsert), {"id": exp_id, "s": json.dumps(state)})
                await conn.execute(text("UPDATE experiments SET updated_at = :ts WHERE id = :id"),
                                   {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "id": exp_id})
            else:
                row = (await conn.execute(text("SELECT state_json FROM session_state WHERE id = 1"))).fetchone()
                state = json.loads(row[0] or "{}") if row else {}
                state[key] = value
                await conn.execute(text("UPDATE session_state SET state_json = :s WHERE id = 1"), {"s": json.dumps(state)})

    # ── conversation events ───────────────────────────────────────────────────

    def clear_conversation_events(self, experiment_id: Optional[int] = None) -> None:
        _run(self._clear_conversation_events_async(experiment_id))

    async def _clear_conversation_events_async(self, experiment_id: Optional[int] = None) -> None:
        async with self._engine.begin() as conn:
            if experiment_id and experiment_id > 0:
                await conn.execute(text("DELETE FROM conversation_events WHERE experiment_id = :id"), {"id": experiment_id})
            else:
                await conn.execute(text("DELETE FROM conversation_events"))

    def get_conversation_events(self, experiment_id: Optional[int] = None) -> List[Dict]:
        return _run(self._get_conversation_events_with_lookup(experiment_id))

    async def _get_conversation_events_with_lookup(self, experiment_id: Optional[int] = None) -> List[Dict]:
        async with self._engine.connect() as conn:
            if experiment_id is None:
                exp_id_row = (await conn.execute(
                    text("SELECT value_int FROM app_config WHERE key = 'current_experiment_id'")
                )).fetchone()
                experiment_id = int(exp_id_row[0]) if exp_id_row and exp_id_row[0] else None
            return await self._get_conversation_events_async(conn, experiment_id)

    async def _get_conversation_events_async(self, conn, experiment_id: Optional[int] = None) -> List[Dict]:
        if experiment_id and experiment_id > 0:
            rows = (await conn.execute(
                text("SELECT type, mode, prompt_session_id, timestamp, payload_json FROM conversation_events WHERE experiment_id = :id ORDER BY id"),
                {"id": experiment_id}
            )).fetchall()
        else:
            rows = (await conn.execute(
                text("SELECT type, mode, prompt_session_id, timestamp, payload_json FROM conversation_events ORDER BY id")
            )).fetchall()
        return [{"type": r[0], "mode": r[1], "prompt_session_id": r[2], "timestamp": r[3], "payload": json.loads(r[4] or "{}")} for r in rows]

    def append_conversation_event(self, event_type: str, mode: str, prompt_session_id: str, payload: dict) -> None:
        _run(self._append_conversation_event_async(event_type, mode, prompt_session_id, payload))

    async def _append_conversation_event_async(self, event_type: str, mode: str, prompt_session_id: str, payload: dict) -> None:
        async with self._engine.begin() as conn:
            exp_id_row = (await conn.execute(
                text("SELECT value_int FROM app_config WHERE key = 'current_experiment_id'")
            )).fetchone()
            exp_id = int(exp_id_row[0]) if exp_id_row and exp_id_row[0] else None
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if exp_id and exp_id > 0:
                await conn.execute(text(
                    "INSERT INTO conversation_events (experiment_id, type, mode, prompt_session_id, timestamp, payload_json) VALUES (:eid, :t, :m, :ps, :ts, :p)"
                ), {"eid": exp_id, "t": event_type, "m": mode, "ps": prompt_session_id, "ts": ts, "p": json.dumps(payload)})
            else:
                await conn.execute(text(
                    "INSERT INTO conversation_events (type, mode, prompt_session_id, timestamp, payload_json) VALUES (:t, :m, :ps, :ts, :p)"
                ), {"t": event_type, "m": mode, "ps": prompt_session_id, "ts": ts, "p": json.dumps(payload)})

    # ── workflows ─────────────────────────────────────────────────────────────

    def get_workflows(self) -> Dict[str, Dict]:
        return _run(self._get_workflows_wrapper())

    async def _get_workflows_wrapper(self) -> Dict[str, Dict]:
        async with self._engine.connect() as conn:
            return await self._get_workflows_async(conn)

    async def _get_workflows_async(self, conn) -> Dict[str, Dict]:
        rows = (await conn.execute(text("SELECT id, name, created_at, ml_model_choice FROM workflows"))).fetchall()
        result = {}
        for r in rows:
            wf_id, name, created_at, ml_model_choice = r
            steps = (await conn.execute(
                text("SELECT name, automatic FROM workflow_steps WHERE workflow_id = :id ORDER BY step_order"),
                {"id": wf_id}
            )).fetchall()
            result[name] = {
                "name": name,
                "steps": [{"name": s[0], "automatic": bool(s[1])} for s in steps],
                "ml_model_choice": ml_model_choice,
                "created_at": created_at or "",
            }
        return result

    def save_workflow(self, name: str, steps: List[Dict], ml_model_choice: Optional[str] = None) -> None:
        _run(self._save_workflow_wrapper(name, steps, ml_model_choice))

    async def _save_workflow_wrapper(self, name: str, steps: List[Dict], ml_model_choice: Optional[str] = None) -> None:
        async with self._engine.begin() as conn:
            await self._save_workflow_async(conn, name, steps, ml_model_choice, _is_postgres(self._engine))

    async def _save_workflow_async(self, conn, name: str, steps: List[Dict], ml_model_choice: Optional[str], pg: bool) -> None:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = (await conn.execute(text("SELECT id FROM workflows WHERE name = :n"), {"n": name})).fetchone()
        if row:
            wf_id = row[0]
            await conn.execute(text("DELETE FROM workflow_steps WHERE workflow_id = :id"), {"id": wf_id})
            await conn.execute(text("UPDATE workflows SET created_at = :ca, ml_model_choice = :ml WHERE id = :id"),
                               {"ca": created_at, "ml": ml_model_choice or "", "id": wf_id})
        else:
            await conn.execute(text("INSERT INTO workflows (name, created_at, ml_model_choice) VALUES (:n, :ca, :ml)"),
                               {"n": name, "ca": created_at, "ml": ml_model_choice or ""})
            if pg:
                wf_id = (await conn.execute(text("SELECT id FROM workflows WHERE name = :n"), {"n": name})).fetchone()[0]
            else:
                wf_id = (await conn.execute(text("SELECT last_insert_rowid()"))).fetchone()[0]
        for i, step in enumerate(steps):
            await conn.execute(text(
                "INSERT INTO workflow_steps (workflow_id, step_order, name, automatic) VALUES (:wid, :so, :n, :a)"
            ), {"wid": wf_id, "so": i, "n": step.get("name", ""), "a": int(step.get("automatic", False))})

    def delete_workflow(self, name: str) -> None:
        _run(self._delete_workflow_async(name))

    async def _delete_workflow_async(self, name: str) -> None:
        async with self._engine.begin() as conn:
            row = (await conn.execute(text("SELECT id FROM workflows WHERE name = :n"), {"n": name})).fetchone()
            if row:
                wf_id = row[0]
                await conn.execute(text("DELETE FROM workflow_steps WHERE workflow_id = :id"), {"id": wf_id})
                await conn.execute(text("DELETE FROM workflows WHERE id = :id"), {"id": wf_id})

    def get_workflow_steps(self, workflow_id: int) -> List[Dict]:
        return _run(self._get_workflow_steps_async(workflow_id))

    async def _get_workflow_steps_async(self, workflow_id: int) -> List[Dict]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(
                text("SELECT name, automatic FROM workflow_steps WHERE workflow_id = :id ORDER BY step_order"),
                {"id": workflow_id}
            )).fetchall()
            return [{"name": r[0], "automatic": bool(r[1])} for r in rows]

    # ── uploaded files ────────────────────────────────────────────────────────

    def get_uploaded_files(self) -> List[Dict]:
        return _run(self._get_uploaded_files_wrapper())

    async def _get_uploaded_files_wrapper(self) -> List[Dict]:
        async with self._engine.connect() as conn:
            return await self._get_uploaded_files_async(conn)

    async def _get_uploaded_files_async(self, conn) -> List[Dict]:
        rows = (await conn.execute(text("SELECT name, path, timestamp FROM uploaded_files ORDER BY id"))).fetchall()
        return [{"name": r[0], "path": r[1], "timestamp": r[2]} for r in rows]

    def add_uploaded_file(self, filename: str, path: str) -> None:
        _run(self._add_uploaded_file_async(filename, path))

    async def _add_uploaded_file_async(self, filename: str, path: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO uploaded_files (name, path, timestamp) VALUES (:n, :p, :ts)"
            ), {"n": filename, "p": path, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    # ── session state ─────────────────────────────────────────────────────────

    def clear_session_state(self, keep_keys: Optional[List[str]] = None) -> None:
        _run(self._clear_session_state_async(keep_keys or []))

    async def _clear_session_state_async(self, keep_keys: List[str]) -> None:
        async with self._engine.begin() as conn:
            row = (await conn.execute(text("SELECT state_json FROM session_state WHERE id = 1"))).fetchone()
            state = json.loads(row[0] or "{}") if row else {}
            new_state = {k: v for k, v in state.items() if k in keep_keys}
            await conn.execute(text("UPDATE session_state SET state_json = :s WHERE id = 1"), {"s": json.dumps(new_state)})

    def clear_all_except(self, keep_keys: List[str]) -> None:
        _run(self._clear_all_except_async(keep_keys))

    async def _clear_all_except_async(self, keep_keys: List[str]) -> None:
        async with self._engine.begin() as conn:
            for k in ["api_key", "api_key_source", "start_time"]:
                if k not in keep_keys:
                    await conn.execute(text("DELETE FROM app_config WHERE key = :k"), {"k": k})
            state = dict(DEFAULT_SESSION_STATE)
            state["current_prompt_session_id"] = str(uuid.uuid4())
            state["start_time"] = datetime.now().timestamp()
            await conn.execute(text("UPDATE session_state SET state_json = :s WHERE id = 1"), {"s": json.dumps(state)})

    # ── users ─────────────────────────────────────────────────────────────────

    def create_user(self, user_id: str, name: str = "") -> None:
        _run(self._create_user_async(user_id, name))

    async def _create_user_async(self, user_id: str, name: str) -> None:
        pg = _is_postgres(self._engine)
        async with self._engine.begin() as conn:
            upsert = (
                "INSERT INTO users (id, name, created_at) VALUES (:id, :n, :ca) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name"
            ) if pg else "INSERT OR REPLACE INTO users (id, name, created_at) VALUES (:id, :n, :ca)"
            await conn.execute(text(upsert), {"id": user_id, "n": name or user_id, "ca": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    def get_user(self, user_id: str) -> Optional[Dict]:
        return _run(self._get_user_async(user_id))

    async def _get_user_async(self, user_id: str) -> Optional[Dict]:
        async with self._engine.connect() as conn:
            row = (await conn.execute(text("SELECT id, name, created_at FROM users WHERE id = :id"), {"id": user_id})).fetchone()
            return {"id": row[0], "name": row[1], "created_at": row[2]} if row else None

    def list_users(self) -> List[Dict]:
        return _run(self._list_users_async())

    async def _list_users_async(self) -> List[Dict]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text("SELECT id, name, created_at FROM users ORDER BY created_at DESC"))).fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

    # ── experiments ───────────────────────────────────────────────────────────

    def create_experiment(self, user_id: str, name: str = "") -> int:
        return _run(self._create_experiment_async(user_id, name))

    async def _create_experiment_async(self, user_id: str, name: str) -> int:
        pg = _is_postgres(self._engine)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name = name or f"Experiment {now[:19]}"
        async with self._engine.begin() as conn:
            if pg:
                result = await conn.execute(text(
                    "INSERT INTO experiments (user_id, name, created_at, updated_at) VALUES (:uid, :n, :ca, :ua) RETURNING id"
                ), {"uid": user_id, "n": name, "ca": now, "ua": now})
                exp_id = result.fetchone()[0]
            else:
                await conn.execute(text(
                    "INSERT INTO experiments (user_id, name, created_at, updated_at) VALUES (:uid, :n, :ca, :ua)"
                ), {"uid": user_id, "n": name, "ca": now, "ua": now})
                exp_id = (await conn.execute(text("SELECT last_insert_rowid()"))).fetchone()[0]
            await conn.execute(text(
                "INSERT INTO experiment_data (experiment_id, state_json) VALUES (:id, :s)"
            ), {"id": exp_id, "s": json.dumps(dict(DEFAULT_SESSION_STATE))})
            return exp_id

    def list_experiments(self, user_id: str, limit: int = 50) -> List[Dict]:
        return _run(self._list_experiments_async(user_id, limit))

    async def _list_experiments_async(self, user_id: str, limit: int) -> List[Dict]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, name, created_at, updated_at FROM experiments WHERE user_id = :uid ORDER BY updated_at DESC LIMIT :lim"
            ), {"uid": user_id, "lim": limit})).fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def get_experiment(self, experiment_id: int) -> Optional[Dict]:
        return _run(self._get_experiment_async(experiment_id))

    async def _get_experiment_async(self, experiment_id: int) -> Optional[Dict]:
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT id, user_id, name, created_at, updated_at FROM experiments WHERE id = :id"
            ), {"id": experiment_id})).fetchone()
            return {"id": row[0], "user_id": row[1], "name": row[2], "created_at": row[3], "updated_at": row[4]} if row else None

    def set_current_experiment(self, experiment_id: int, user_id: str = "") -> None:
        _run(self._set_current_experiment_async(experiment_id, user_id))

    async def _set_current_experiment_async(self, experiment_id: int, user_id: str) -> None:
        async with self._engine.begin() as conn:
            if user_id:
                await self._set_config_value_async(conn, "current_user_id", user_id)
            await self._set_config_value_async(conn, "current_experiment_id", experiment_id)

    def load_experiment_into_session(self, experiment_id: int) -> None:
        _run(self._load_experiment_into_session_async(experiment_id))

    async def _load_experiment_into_session_async(self, experiment_id: int) -> None:
        async with self._engine.begin() as conn:
            row = (await conn.execute(text(
                "SELECT state_json FROM experiment_data WHERE experiment_id = :id"
            ), {"id": experiment_id})).fetchone()
            if row and row[0]:
                await conn.execute(text("UPDATE session_state SET state_json = :s WHERE id = 1"), {"s": row[0]})

    # ── negative hypotheses ───────────────────────────────────────────────────

    def add_negative_hypothesis(self, hypothesis_text: str, status: str, research_question: str = "", analysis_summary: str = "", context_json: Optional[str] = None) -> None:
        _run(self._add_negative_hypothesis_async(hypothesis_text, status, research_question, analysis_summary, context_json))

    async def _add_negative_hypothesis_async(self, hypothesis_text: str, status: str, research_question: str, analysis_summary: str, context_json: Optional[str]) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO negative_hypotheses (hypothesis_text, status, research_question, analysis_summary, context_json, created_at) VALUES (:ht, :st, :rq, :as_, :cj, :ca)"
            ), {"ht": hypothesis_text, "st": status, "rq": research_question or "", "as_": analysis_summary or "", "cj": context_json, "ca": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    def get_negative_hypotheses(self, limit: Optional[int] = None) -> List[Dict]:
        return _run(self._get_negative_hypotheses_async(limit))

    async def _get_negative_hypotheses_async(self, limit: Optional[int]) -> List[Dict]:
        async with self._engine.connect() as conn:
            sql = "SELECT hypothesis_text, status, research_question, analysis_summary, created_at FROM negative_hypotheses ORDER BY id DESC"
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
            rows = (await conn.execute(text(sql))).fetchall()
            return [{"hypothesis_text": r[0], "status": r[1], "research_question": r[2] or "", "analysis_summary": r[3] or "", "created_at": r[4] or ""} for r in rows]

    # ── hypothesis outcomes ───────────────────────────────────────────────────

    def add_hypothesis_outcome(self, hypothesis_text: str, status: str, material_hint: str = "", evidence_summary: str = "", source: str = "orchestrator") -> None:
        _run(self._add_hypothesis_outcome_async(hypothesis_text, status, material_hint, evidence_summary, source))

    async def _add_hypothesis_outcome_async(self, hypothesis_text: str, status: str, material_hint: str, evidence_summary: str, source: str) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO hypothesis_outcomes (hypothesis_text, material_hint, status, evidence_summary, source, created_at) VALUES (:ht, :mh, :st, :es, :src, :ca)"
            ), {"ht": hypothesis_text, "mh": material_hint or "", "st": status, "es": evidence_summary or "", "src": source or "orchestrator", "ca": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    def get_hypothesis_outcomes(self, limit: Optional[int] = 200) -> List[Dict]:
        return _run(self._get_hypothesis_outcomes_async(limit))

    async def _get_hypothesis_outcomes_async(self, limit: Optional[int]) -> List[Dict]:
        async with self._engine.connect() as conn:
            sql = "SELECT hypothesis_text, material_hint, status, evidence_summary, source, created_at FROM hypothesis_outcomes ORDER BY id DESC"
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
            rows = (await conn.execute(text(sql))).fetchall()
            return [{"hypothesis_text": r[0], "material_hint": r[1] or "", "status": r[2], "evidence_summary": r[3] or "", "source": r[4] or "", "created_at": r[5] or ""} for r in rows]
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/db/test_database_manager.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
python3 -m pytest tests/ --ignore=tests/test_mcp_orchestrator_logic.py -q
```

Expected: 36+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add app/tools/database.py
git commit -m "feat(db): rewrite DatabaseManager with SQLAlchemy async, dual SQLite/Postgres support"
```

---

## Task 3: Update checkpointer, init_db, and config

**Files:**
- Modify: `app/graph/checkpointer.py`
- Modify: `init_db.py`
- Modify: `app/core/config.py`

**Interfaces:**
- Consumes: `get_db_url() -> str` from `app.db.engine`
- `init_checkpointer()` signature unchanged — still returns `AsyncSqliteSaver | AsyncPostgresSaver`

- [ ] **Step 1: Write failing test for checkpointer selection**

Add to `tests/db/test_engine.py`:

```python
async def test_init_checkpointer_returns_sqlite_saver(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/ckpt.db")
    import importlib, app.db.engine as eng, app.graph.checkpointer as ckpt
    importlib.reload(eng); eng._engine = None
    importlib.reload(ckpt); ckpt._checkpointer = None; ckpt._conn = None
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    saver = await ckpt.init_checkpointer()
    assert isinstance(saver, AsyncSqliteSaver)
    await ckpt.close_checkpointer()
```

- [ ] **Step 2: Run test to verify it fails (import error expected if checkpointer not updated yet)**

```bash
python3 -m pytest tests/db/test_engine.py::test_init_checkpointer_returns_sqlite_saver -v
```

- [ ] **Step 3: Update `app/graph/checkpointer.py`**

Replace the entire file:

```python
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
```

- [ ] **Step 4: Update `app/core/config.py`**

Change line 25 (`database_url`) default to read from env first. The `pydantic-settings` `BaseSettings` already reads env vars automatically — just ensure the default makes sense:

```python
    database_url: str = "sqlite+aiosqlite:///./data/polaris.db"
```

(Change the existing `"sqlite:///./data/polaris.db"` to `"sqlite+aiosqlite:///./data/polaris.db"` to match the new URL format.)

- [ ] **Step 5: Update `init_db.py`**

Replace the `init_database()` function:

```python
def init_database() -> str:
    """
    Initialize the database. Runs Alembic migrations for Postgres,
    or SQLite schema init for SQLite.
    Returns a status string.
    """
    import os
    import subprocess
    import sys
    from app.db.engine import get_db_url

    url = get_db_url()
    if url.startswith("postgresql"):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError(f"Alembic migration failed: {result.stderr}")
        print(result.stdout)
        return "postgres"
    else:
        from app.tools.database import DatabaseManager
        db = DatabaseManager()
        db.init_schema()
        db.ensure_defaults()
        db_path = url.replace("sqlite+aiosqlite:///", "")
        return db_path
```

Also update `__main__` block at bottom to use the new return value:

```python
if __name__ == "__main__":
    try:
        result = init_database()
        print(f"Database initialized: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/db/ -v
```

Expected: all pass.

- [ ] **Step 7: Run full suite**

```bash
python3 -m pytest tests/ --ignore=tests/test_mcp_orchestrator_logic.py -q
```

Expected: 36+ passed.

- [ ] **Step 8: Commit**

```bash
git add app/graph/checkpointer.py init_db.py app/core/config.py
git commit -m "feat(db): update checkpointer and init_db for Postgres/SQLite dual support"
```

---

## Task 4: Complete Alembic migration (9 missing tables)

**Files:**
- Modify: `migrations/versions/001_initial_postgres.py`

**Interfaces:**
- Produces: complete `upgrade()` covering all 14 tables matching the DatabaseManager schema

- [ ] **Step 1: Verify current migration only has 5 tables**

```bash
grep "create_table" migrations/versions/001_initial_postgres.py
```

Expected: 5 `create_table` calls.

- [ ] **Step 2: Replace the migration file**

Replace `migrations/versions/001_initial_postgres.py` entirely:

```python
"""Initial schema — all 14 tables."""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_int", sa.BigInteger(), nullable=True),
        sa.Column("value_real", sa.Float(), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "experimental_constraints",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("techniques_json", sa.Text(), nullable=True),
        sa.Column("equipment_json", sa.Text(), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("focus_areas_json", sa.Text(), nullable=True),
        sa.Column("liquid_handling_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "jupyter_config",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("server_url", sa.Text(), nullable=True),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("upload_enabled", sa.Integer(), nullable=True),
        sa.Column("notebook_path", sa.Text(), nullable=True),
    )
    op.create_table(
        "experiment_data",
        sa.Column("experiment_id", sa.BigInteger(), sa.ForeignKey("experiments.id"), primary_key=True),
        sa.Column("state_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "conversation_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("prompt_session_id", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "agent_usage_counts",
        sa.Column("agent_name", sa.String(128), primary_key=True),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "workflows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.Column("ml_model_choice", sa.Text(), nullable=True),
    )
    op.create_table(
        "workflow_steps",
        sa.Column("workflow_id", sa.BigInteger(), sa.ForeignKey("workflows.id"), nullable=False),
        sa.Column("step_order", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("automatic", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("workflow_id", "step_order"),
    )
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
    )
    op.create_table(
        "session_state",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("state_json", sa.Text(), nullable=True),
    )
    op.create_table(
        "negative_hypotheses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=True),
        sa.Column("analysis_summary", sa.Text(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "hypothesis_outcomes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_text", sa.Text(), nullable=False),
        sa.Column("material_hint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "hypothesis_outcomes", "negative_hypotheses", "session_state",
        "uploaded_files", "workflow_steps", "workflows", "agent_usage_counts",
        "conversation_events", "experiment_data", "jupyter_config",
        "experimental_constraints", "app_config", "experiments", "users",
    ]:
        op.drop_table(table)
```

- [ ] **Step 3: Verify migration runs against a local SQLite (dry-run check)**

```bash
DATABASE_URL=sqlite:///./data/test_migration.db python3 -m alembic upgrade head 2>&1
```

Expected: `Running upgrade  -> 001` with no errors. (SQLite dialect handles Alembic differently — if it fails with SQLite, that's OK since Alembic targets Postgres. The test confirms the SQL is valid.)

Clean up: `rm -f data/test_migration.db`

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/001_initial_postgres.py
git commit -m "feat(db): complete Alembic migration with all 14 tables"
```

---

## Task 5: Render deployment files

**Files:**
- Create: `backend-api/render.yaml`
- Create: `backend-api/scripts/start.sh`
- Modify: `backend-api/Dockerfile`
- Modify: `backend-api/scripts/migrate_sqlite_to_postgres.py`

**Interfaces:**
- `start.sh` replaces `railway-start.sh` — identical behavior, platform-neutral name
- `render.yaml` wires Render Web Service + managed Postgres

- [ ] **Step 1: Create `scripts/start.sh`**

```bash
#!/bin/sh
set -e

python init_db.py

PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

Make executable:
```bash
chmod +x scripts/start.sh
```

- [ ] **Step 2: Update `Dockerfile`**

Change the two lines that reference `railway-start.sh`:

```dockerfile
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh
```

And the CMD:
```dockerfile
CMD ["/app/scripts/start.sh"]
```

(Remove the old `railway-start.sh` lines.)

- [ ] **Step 3: Create `render.yaml`**

```yaml
services:
  - type: web
    name: polaris-api
    runtime: docker
    dockerfilePath: ./Dockerfile
    healthCheckPath: /api/v1/health
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: polaris-db
          property: connectionString
      - key: CORS_ORIGINS
        value: http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081,http://127.0.0.1:8081
      - key: AUTH_DISABLED
        value: "true"
      - key: LLM_PROVIDER
        sync: false
      - key: LLM_API_KEY
        sync: false
      - key: POLARIS_RESULTS_DIR
        value: /data/results

databases:
  - name: polaris-db
    databaseName: polaris
    user: polaris
    plan: free
```

**Note:** `CORS_ORIGINS` should be updated in the Render dashboard after deployment to include the actual Vercel URL (e.g. `https://polaris.vercel.app`). The value above is a safe default for initial deploy.

- [ ] **Step 4: Extend `scripts/migrate_sqlite_to_postgres.py`**

Replace the entire file:

```python
#!/usr/bin/env python3
"""
One-time migration: copy all 14 tables from local SQLite to Render Postgres.

Usage:
    POLARIS_SQLITE_PATH=./data/polaris.db \
    DATABASE_URL=postgresql+asyncpg://user:pw@host/db \
    python scripts/migrate_sqlite_to_postgres.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

from sqlalchemy import create_engine, text

SQLITE_PATH = os.getenv("POLARIS_SQLITE_PATH", "./data/polaris.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Tables with simple row-by-row copy (all columns TEXT/INT)
SIMPLE_TABLES = [
    "users",
    "agent_usage_counts",
    "workflows",
    "workflow_steps",
    "uploaded_files",
    "negative_hypotheses",
    "hypothesis_outcomes",
]

# Tables with JSON columns that need decode/re-encode
JSON_TABLES = {
    "app_config": [],          # value_json column is already TEXT, no special handling
    "experimental_constraints": ["techniques_json", "equipment_json", "parameters_json", "focus_areas_json", "liquid_handling_json"],
    "jupyter_config": [],
    "experiment_data": ["state_json"],
    "conversation_events": ["payload_json"],
    "session_state": ["state_json"],
}


def _pg_url(url: str) -> str:
    """Convert asyncpg URL to sync psycopg URL for migration script."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def main() -> int:
    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
        print("Set DATABASE_URL to a postgresql:// connection string", file=sys.stderr)
        return 1
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite not found: {SQLITE_PATH}", file=sys.stderr)
        return 1

    engine = create_engine(_pg_url(DATABASE_URL))
    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_sqlite.row_factory = sqlite3.Row

    with engine.begin() as pg:
        # Simple tables
        for table in SIMPLE_TABLES:
            try:
                rows = conn_sqlite.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                print(f"  {table}: not found in SQLite, skipping")
                continue
            if not rows:
                print(f"  {table}: 0 rows, skipping")
                continue
            cols = rows[0].keys()
            placeholders = ", ".join(f":{c}" for c in cols)
            col_list = ", ".join(cols)
            conflict_col = "id" if "id" in cols else cols[0]
            update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != conflict_col)
            upsert = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}"
            for row in rows:
                pg.execute(text(upsert), dict(row))
            print(f"  {table}: {len(rows)} rows migrated")

        # Tables with JSON columns
        for table, json_cols in JSON_TABLES.items():
            try:
                rows = conn_sqlite.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                print(f"  {table}: not found in SQLite, skipping")
                continue
            if not rows:
                print(f"  {table}: 0 rows, skipping")
                continue
            cols = rows[0].keys()
            col_list = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            pk_col = "id" if "id" in cols else ("key" if "key" in cols else cols[0])
            if pk_col == "key":
                upsert = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT (key) DO UPDATE SET {', '.join(f'{c}=EXCLUDED.{c}' for c in cols if c != 'key')}"
            else:
                upsert = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT ({pk_col}) DO NOTHING"
            for row in rows:
                params = dict(row)
                # Validate JSON columns — re-encode if needed
                for jcol in json_cols:
                    if jcol in params and params[jcol] is not None:
                        try:
                            parsed = json.loads(params[jcol])
                            params[jcol] = json.dumps(parsed)
                        except (json.JSONDecodeError, TypeError):
                            params[jcol] = None
                pg.execute(text(upsert), params)
            print(f"  {table}: {len(rows)} rows migrated")

    print("\nMigration complete. Run: DATABASE_URL=... alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Verify Dockerfile builds locally**

```bash
docker build -t polaris-api-test . 2>&1 | tail -10
```

Expected: `Successfully built ...` (or equivalent).

- [ ] **Step 6: Run full test suite**

```bash
python3 -m pytest tests/ --ignore=tests/test_mcp_orchestrator_logic.py -q
```

Expected: 36+ passed.

- [ ] **Step 7: Commit**

```bash
git add render.yaml scripts/start.sh scripts/migrate_sqlite_to_postgres.py Dockerfile
git commit -m "feat(deploy): add render.yaml, start.sh, and extend data migration script"
```

---

## Task 6: Deployment verification and frontend wiring

This task has **no code changes** — it is the deployment checklist.

**Files:**
- No changes

- [ ] **Step 1: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Create Render Web Service**

1. Go to [render.com](https://render.com) → New → Web Service
2. Connect your GitHub repo (`POLARIS-Ahmadi-OFFICIAL/backend-api`)
3. Render detects `render.yaml` and pre-fills the service + database config
4. Set secret env vars in the Render dashboard (not in `render.yaml`):
   - `LLM_PROVIDER` = `qwen` or `gemini`
   - `LLM_API_KEY` = your API key
5. Click **Deploy**

- [ ] **Step 3: Verify health check passes**

Once deployed, Render shows the public URL (e.g. `https://polaris-api.onrender.com`).

```bash
curl https://polaris-api.onrender.com/api/v1/health
```

Expected: `{"status": "ok"}` or similar 200 response.

- [ ] **Step 4: Update CORS_ORIGINS on Render**

In the Render dashboard → Environment → `CORS_ORIGINS`, add your Vercel URL:

```
http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081,http://127.0.0.1:8081,https://YOUR-APP.vercel.app
```

Click **Save** — Render redeploys automatically.

- [ ] **Step 5: Update Vercel environment variable**

In the Vercel dashboard → Project Settings → Environment Variables:

```
NEXT_PUBLIC_API_URL = https://polaris-api.onrender.com
```

Redeploy from Vercel dashboard (or push a commit to trigger it).

- [ ] **Step 6: Update mobile app env**

In `mobile-development/.env` (or EAS `eas.json` build profile for production):

```
EXPO_PUBLIC_API_URL=https://polaris-api.onrender.com
```

Build and publish a new Expo update:
```bash
cd mobile-development
npx expo publish   # or eas update for EAS
```

- [ ] **Step 7: Run data migration (optional — if you have existing SQLite data)**

From your local machine with the production `DATABASE_URL` from Render:

```bash
POLARIS_SQLITE_PATH=./data/polaris.db \
DATABASE_URL=postgresql+asyncpg://polaris:PASSWORD@HOST/polaris \
python scripts/migrate_sqlite_to_postgres.py
```

Expected output: each of the 14 tables with row counts.

- [ ] **Step 8: Smoke test the API from both clients**

Web:
- Open the Vercel app, try creating a hypothesis — verify it reaches Render backend

Mobile:
- Open Expo app — check Settings → API URL shows the Render URL, try one agent call

---

## Verification Commands (run any time)

```bash
# All tests pass
python3 -m pytest tests/ --ignore=tests/test_mcp_orchestrator_logic.py -q

# SQLite path still works (no DATABASE_URL set)
python3 -c "from app.tools.database import DatabaseManager; db = DatabaseManager(); db.init_schema(); db.ensure_defaults(); print('SQLite OK:', db.get('llm_provider'))"

# Imports clean
python3 -c "from app.db.engine import get_db_url, get_async_engine; print('engine OK')"
python3 -c "from app.graph.checkpointer import get_checkpointer; print('checkpointer import OK')"
```
