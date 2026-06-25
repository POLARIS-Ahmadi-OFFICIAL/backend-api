# POLARIS — Postgres Migration & Render Deployment Design

**Date:** 2026-06-24
**Status:** Approved

---

## 1. Goals

- Replace the raw `sqlite3` `DatabaseManager` with SQLAlchemy Core async so the same codebase works with both Postgres (production/Render) and SQLite (local dev/desktop)
- Deploy the FastAPI backend on Render as a public Web Service
- Wire both the Vercel web frontend and the Expo mobile app to the Render backend URL
- Keep `docker compose up` working for local development

---

## 2. Database Layer

### 2.1 Connection selection

`DATABASE_URL` environment variable drives the database backend:

| Value | Driver | Use case |
|---|---|---|
| `postgresql+asyncpg://...` | asyncpg | Render production, local Docker Compose |
| `sqlite+aiosqlite:///./data/polaris.db` | aiosqlite | Local uvicorn dev, desktop app |

If `DATABASE_URL` is unset, the app defaults to `sqlite+aiosqlite:///./data/polaris.db`.

### 2.2 DatabaseManager rewrite

`app/tools/database.py` is rewritten using **SQLAlchemy Core async**:

- `sqlite3.connect()` + thread-local pattern → `create_async_engine(DATABASE_URL)` + `AsyncSession` from a shared pool
- All parameterized queries use `:named` parameters (compatible with both asyncpg and aiosqlite)
- `INSERT OR REPLACE INTO` → `INSERT INTO ... ON CONFLICT (...) DO UPDATE SET ...`
- `sqlite3.lastrowid` / `last_insert_rowid()` → SQLAlchemy `result.inserted_primary_key`
- WAL pragma (`PRAGMA journal_mode=WAL`) removed — Postgres doesn't support it; SQLite path keeps it via `@event.listens_for(engine_sync, "connect")`
- All 14 tables preserved identically in schema:
  `app_config`, `experimental_constraints`, `jupyter_config`, `users`, `experiments`, `experiment_data`, `conversation_events`, `agent_usage_counts`, `workflows`, `workflow_steps`, `uploaded_files`, `session_state`, `negative_hypotheses`, `hypothesis_outcomes`

The `MemoryManager` (`app/tools/memory.py`) and all agent code above it are **unchanged** — they continue to call the same `get_var` / `set_var` / `log_event` / `insert_interaction` API.

### 2.3 New dependencies

```toml
"sqlalchemy[asyncio]>=2.0.0",
"asyncpg>=0.29.0",
"aiosqlite>=0.20.0",   # already present via langgraph-checkpoint-sqlite
```

`aiosqlite` is already installed as a transitive dependency of `langgraph-checkpoint-sqlite`.

### 2.4 LangGraph checkpointer

`app/graph/checkpointer.py` selects checkpointer based on `DATABASE_URL`:

- Postgres → `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`
- SQLite → `AsyncSqliteSaver` from `langgraph-checkpoint-sqlite` (existing)

New dependency:
```toml
"langgraph-checkpoint-postgres>=1.0.0",
"psycopg[binary,pool]>=3.1.0",   # AsyncPostgresSaver uses psycopg3
```

### 2.5 Alembic migrations

`migrations/versions/001_initial_postgres.py` is extended to cover all 14 tables (currently only covers 5: `users`, `experiments`, `app_config`, `experiment_data`, `conversation_events`). The 9 missing tables are added:
`experimental_constraints`, `jupyter_config`, `agent_usage_counts`, `workflows`, `workflow_steps`, `uploaded_files`, `session_state`, `negative_hypotheses`, `hypothesis_outcomes`

`alembic.ini` default URL is updated to `sqlite+aiosqlite:///./data/polaris.db` for local use. `migrations/env.py` already reads `DATABASE_URL` env var — no change needed.

### 2.6 init_db.py

Updated to be database-aware:
- If `DATABASE_URL` starts with `postgresql` → run `alembic upgrade head`
- Otherwise → run existing SQLite schema init (`DatabaseManager().init_schema()`)

---

## 3. Render Deployment

### 3.1 Web Service configuration

Render Web Service pointed at the existing `Dockerfile`. No Dockerfile changes required — `railway-start.sh` already handles `PORT` injection.

`render.yaml` (Infrastructure as Code) defines:
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
        value: https://polaris.vercel.app,http://localhost:3000,http://localhost:8080
      - key: AUTH_DISABLED
        value: false
      - key: LLM_PROVIDER
        sync: false   # set manually in Render dashboard
      - key: LLM_API_KEY
        sync: false   # set manually in Render dashboard

databases:
  - name: polaris-db
    databaseName: polaris
    user: polaris
    plan: free
```

Render injects `DATABASE_URL` as `postgresql+asyncpg://...` automatically when a database is linked.

### 3.2 CORS

`CORS_ORIGINS` on Render includes the Vercel deployment URL. Mobile clients send requests directly to Render — since their IPs are dynamic, mobile CORS is handled by including the Render URL in `CORS_ORIGINS` and relying on JWT for identity validation rather than origin restrictions. The CORS middleware in `app/main.py` reads `CORS_ORIGINS` from env — no code change needed beyond setting the correct value.

### 3.3 Startup sequence

`railway-start.sh` is renamed to `start.sh` (platform-neutral name) and updated:
```sh
#!/bin/sh
set -e
python init_db.py          # runs alembic migrate (Postgres) or init_schema (SQLite)
PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

---

## 4. Local Development

### 4.1 docker-compose.yml (unchanged)

The existing `docker-compose.yml` continues to work as-is for local Docker-based development:
- Backend container connects to local Postgres via `DATABASE_URL: postgresql+asyncpg://polaris:polaris@db:5432/polaris`
- `docker compose up` starts API + Postgres

### 4.2 Direct uvicorn (no Docker)

Running `uvicorn app.main:app` without `DATABASE_URL` set falls back to SQLite. Desktop app continues to work this way unchanged.

---

## 5. Data Migration

`scripts/migrate_sqlite_to_postgres.py` is extended to cover all 14 tables (currently handles 5). Run once manually after Render Postgres is provisioned:

```bash
POLARIS_SQLITE_PATH=./data/polaris.db \
DATABASE_URL=postgresql+asyncpg://... \
python scripts/migrate_sqlite_to_postgres.py
```

JSON columns (`value_json`, `state_json`, `payload_json`) are decoded from SQLite text and re-encoded as native Postgres JSONB. After the migration, Postgres is the source of truth for production.

---

## 6. Frontend Wiring

### 6.1 Vercel (web)

In the Vercel dashboard, update the environment variable:
```
NEXT_PUBLIC_API_URL=https://polaris-api.onrender.com
```

No code changes to `web-frontend/` required.

### 6.2 Expo (mobile)

In `mobile-development/.env` (or EAS build profile):
```
EXPO_PUBLIC_API_URL=https://polaris-api.onrender.com
```

The existing `getApiBase()` in `src/lib/api-base.ts` already reads this — no code changes required.

---

## 7. New Files

| File | Purpose |
|---|---|
| `backend-api/render.yaml` | Render Infrastructure as Code — service + database definition |
| `backend-api/scripts/start.sh` | Renamed from `railway-start.sh`, platform-neutral |

## 8. Modified Files

| File | Change |
|---|---|
| `app/tools/database.py` | Full rewrite: SQLAlchemy Core async, dual-driver support |
| `app/graph/checkpointer.py` | Select `AsyncPostgresSaver` vs `AsyncSqliteSaver` from `DATABASE_URL` |
| `app/core/config.py` | Default `database_url` reads `DATABASE_URL` env var first |
| `migrations/versions/001_initial_postgres.py` | Add 9 missing tables |
| `alembic.ini` | Update default URL to `sqlite+aiosqlite:///./data/polaris.db` |
| `init_db.py` | Branch on Postgres vs SQLite |
| `pyproject.toml` | Add `sqlalchemy[asyncio]`, `asyncpg`, `langgraph-checkpoint-postgres`, `psycopg[binary,pool]` |
| `scripts/migrate_sqlite_to_postgres.py` | Extend to all 14 tables + JSONB handling |
| `Dockerfile` | Update `COPY` for renamed `start.sh`; remove `railway-start.sh` reference |

---

## 9. Out of Scope

- Authentication (`AUTH_DISABLED` remains configurable; Supabase JWT wiring is a separate project)
- Moving the Next.js frontend off Vercel
- Horizontal scaling / read replicas (single Render instance is sufficient for initial public launch)

