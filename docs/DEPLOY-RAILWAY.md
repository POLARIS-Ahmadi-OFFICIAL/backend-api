# Deploy POLARIS API on Railway

Railway runs the **backend-api** repo. Vercel runs **web-frontend** and calls this API via `NEXT_PUBLIC_API_URL`.

## 1. Create the Railway service

1. Open [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Select **`POLARIS-Ahmadi-OFFICIAL/backend-api`** (or your fork).
3. Railway should detect the **Dockerfile** (`railway.toml` points at it). No custom start command is required.

## 2. Persistent storage (required)

The API uses **SQLite** on disk. Without a volume, data is lost on every deploy.

1. In the service → **Volumes** → **Add Volume**.
2. Mount path: **`/data`**
3. Set variables (Settings → Variables):

| Variable | Value |
|----------|--------|
| `POLARIS_DB_PATH` | `/data/polaris.db` |
| `POLARIS_RESULTS_DIR` | `/data/results` |

## 3. Environment variables

Copy from [`.env.example`](../.env.example) and set in Railway → **Variables**:

| Variable | Production guidance |
|----------|---------------------|
| `AUTH_DISABLED` | `false` when using Supabase auth; `true` only for demos |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (Settings → API → JWT) |
| `CORS_ORIGINS` | Comma-separated browser origins, e.g. `https://your-app.vercel.app,http://localhost:3000` |
| `HUGGINGFACE_API_KEY` or `GEMINI_API_KEY` | LLM keys (or configure via Settings in the app after deploy) |
| `LLM_PROVIDER` | `qwen` or `gemini` |
| `DEBUG` | `false` |

Railway sets **`PORT`** automatically; the start script binds to it.

Optional:

| Variable | Purpose |
|----------|---------|
| `GEMINI_MIN_INTERVAL_SEC` | `6` (default) — reduces Gemini 429s |
| `HYPOTHESIS_FAST_MODE` | `1` (default) — fewer hypothesis LLM calls |

## 4. Public URL

1. Service → **Settings** → **Networking** → **Generate Domain**.
2. Note the URL, e.g. `https://backend-api-production-xxxx.up.railway.app`.
3. Health check: `GET https://<your-domain>/api/v1/health` → `{"status":"ok",...}`.

## 5. Connect Vercel (web-frontend)

In the Vercel project → **Settings** → **Environment Variables**:

```bash
NEXT_PUBLIC_API_URL=https://<your-railway-domain>
```

Use the Railway URL **without** `/api/v1` (the Next.js proxy adds that path).

Redeploy Vercel after saving.

Add the same Vercel URL to Railway **`CORS_ORIGINS`** (comma-separated, no trailing slash on paths).

## 6. Local full stack (unchanged)

From `web-frontend`:

```bash
npm run dev:stack
```

That starts API `:8080`, Next `:3000`, and Expo — only on your machine, not on Vercel.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Vercel shows API offline | Check `NEXT_PUBLIC_API_URL`, Railway deploy logs, health URL |
| CORS errors in browser | Add exact Vercel preview/production URL to `CORS_ORIGINS` |
| 401 on API routes | Set `AUTH_DISABLED=false` and valid Supabase env, or sign in on web |
| Data resets after deploy | Attach volume at `/data` and set `POLARIS_DB_PATH` |
| Build slow / large image | Normal (scientific Python deps). Consider `ml` extras off in Dockerfile if you trim later |

## Postgres (optional, advanced)

Alembic migrations under `migrations/` target Postgres, but the live app still uses **SQLite** via `DatabaseManager`. For Postgres-backed production you would need further wiring; the volume + SQLite path above is the supported Railway setup today.
