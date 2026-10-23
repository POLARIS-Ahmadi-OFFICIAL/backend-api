# backend-api

POLARIS FastAPI backend: LLM research agents, experiment watcher, MCP orchestrator, phase-mapper pipeline, and persistence.

New to POLARIS? Start with the [onboarding guide](https://github.com/POLARIS-Ahmadi-OFFICIAL/.github/blob/main/ONBOARDING.md).

## Quick start

Requires **Python 3.12+**.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python init_db.py
uvicorn app.main:app --reload --port 8080
```

Health: `GET http://localhost:8080/api/v1/health` · Interactive API docs: `http://localhost:8080/docs`

The default `.env` uses local SQLite (`./data/polaris.db`) and `AUTH_DISABLED=true`, so local work needs no Supabase or Postgres.

### With Postgres (Docker Compose)

```bash
docker compose up
```

Starts the API on `:8080` against a local Postgres 16 container.

### Run API + web + mobile together

From [web-frontend](https://github.com/POLARIS-Ahmadi-OFFICIAL/web-frontend) (with this repo's `.venv` ready and both repos cloned side by side):

```bash
npm run dev:stack
```

## Tests

```bash
pytest tests/ -q
ruff check app tests --ignore E501
```

CI runs the same on every push and PR to `main`, plus a Docker build.

## Database

`DATABASE_URL` selects the backend:

| Value | Use |
|-------|-----|
| `sqlite:///./data/polaris.db` (default; also used when unset) | Local dev, desktop app |
| `postgresql+asyncpg://…` | Production (Render), Docker Compose |

Schema migrations live in `migrations/` (Alembic): `alembic upgrade head`. To copy an existing SQLite DB into Postgres: `scripts/migrate_sqlite_to_postgres.py`.

## Deploy

Production runs on **Render** (`render.yaml`: Docker web service + managed Postgres). See **[docs/DEPLOY.md](./docs/DEPLOY.md)**.

## LLM providers

- **Qwen** via the Hugging Face router (`HUGGINGFACE_API_KEY`)
- **Google Gemini** (`GEMINI_API_KEY` or `GOOGLE_API_KEY`)

Keys can also be saved at runtime with `PATCH /api/v1/settings` (Settings → General in the apps). List models: `GET /api/v1/llm/providers`.

### Hypothesis agent performance

The flow is **inherently multi-step** (clarify → explore → refine → synthesize). Each step is a separate LLM round-trip, so latency adds up, especially on the Gemini free tier with `GEMINI_MIN_INTERVAL_SEC=6` (default), which spaces calls to avoid 429s.

| Setting | Default | Effect |
|--------|---------|--------|
| `HYPOTHESIS_FAST_MODE` | `1` | After clarify, one combined call for Socratic pass + 3 thoughts (~2 calls on submit instead of ~4) |
| `HYPOTHESIS_SKIP_READINESS_CHECK` | `1` | No extra LLM call before each next-step pick |
| `HYPOTHESIS_SKIP_SOCRATIC_ANSWERS` | off | Set `1` to skip the self-answer step |
| `HYPOTHESIS_SKIP_ANALYSIS_ON_GENERATE` | off | Set `1` to return the hypothesis only (skips the analysis rubric) |
| `HYPOTHESIS_CONTEXT_MAX_CHARS` | `4500` | Truncates long prompts |

**Provider tips:** prefer `gemini-2.0-flash-lite` or Qwen on a paid tier; lower `GEMINI_MIN_INTERVAL_SEC` only if your quota allows. After a 429, wait ~60s and retry.

## Layout

| Path | Contents |
|------|----------|
| `app/main.py` | FastAPI app factory |
| `app/api/v1/` | REST routes (contract: [shared-types](https://github.com/POLARIS-Ahmadi-OFFICIAL/shared-types) `openapi/polaris-v1.yaml`) |
| `app/agents/` | Hypothesis, experiment, analysis, curve-fitting, ML-models, watcher agents |
| `app/tools/` | Agent tooling: LLM client, literature agent bridge, MCP orchestrator, phase-mapper runner |
| `app/graph/`, `app/llm/` | LangGraph workflows and LLM provider wiring |
| `app/db/` | SQLAlchemy async engine (SQLite or Postgres) |
| `app/services/`, `app/core/` | Business logic, config, auth |
| `app/watcher/` | File watcher for incoming experiment data |
| `literature_agent/` | LiteratureAgent pipeline (search, extraction, knowledge graph) |
| `migrations/` | Alembic migrations |
| `tests/` | pytest |
| `docs/superpowers/` | Design specs and implementation plans for major features |
| `docs/archive/` | Historical docs (monolith migration, old Railway deploy) |

## Auth

Local and desktop use `AUTH_DISABLED=true` (the default in `.env.example`) and never touch Supabase. Hosted web uses Supabase GitHub login: set `AUTH_DISABLED=false`, `SUPABASE_URL`, and `SUPABASE_JWT_SECRET`.

## History

Split out of the [polaris_ahmadi](https://github.com/CyberA183/polaris_ahmadi) Streamlit monolith at v1.0.0; see [docs/archive/MIGRATION.md](./docs/archive/MIGRATION.md).
