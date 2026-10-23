# Deploy the POLARIS API (Render)

Render runs **backend-api** from `render.yaml`: a Docker web service (`polaris-api`) plus a managed Postgres database (`polaris-db`). Vercel runs **web-frontend** and calls this API through `NEXT_PUBLIC_API_URL`.

## 1. Create the services

1. Render → **New** → **Blueprint** → select `POLARIS-Ahmadi-OFFICIAL/backend-api`.
2. Render reads `render.yaml`, creates the web service and the database, and injects `DATABASE_URL` from the database automatically.
3. The container runs `scripts/start.sh`, which runs `python init_db.py` and then starts uvicorn on Render's `PORT`.

Health check: `GET https://<service>.onrender.com/api/v1/health` → `{"status":"ok",...}`.

## 2. Environment variables

Set in the Render dashboard (values marked `sync: false` in `render.yaml` are never committed):

| Variable | Guidance |
|----------|----------|
| `DATABASE_URL` | Injected from `polaris-db`; don't set by hand |
| `AUTH_DISABLED` | `false` for real users (Supabase login); `true` only for demos. `render.yaml` ships `true` |
| `SUPABASE_URL`, `SUPABASE_JWT_SECRET` | Required when `AUTH_DISABLED=false` |
| `CORS_ORIGINS` | Comma-separated browser origins. Add the Vercel URL after the first deploy |
| `LLM_PROVIDER` | `qwen` or `gemini` |
| `HUGGINGFACE_API_KEY` / `GEMINI_API_KEY` | LLM keys (or save later via Settings in the app) |
| `POLARIS_RESULTS_DIR` | `/data/results` (from `render.yaml`) |
| `SMTP_*`, `FEEDBACK_TO_EMAIL` | Optional; enables the in-app feedback form email |

See [`.env.example`](../.env.example) for the full list.

## 3. Database migrations

`init_db.py` creates tables on boot. For schema changes, run Alembic against the Render database:

```bash
DATABASE_URL=<render external connection string> alembic upgrade head
```

## 4. Connect Vercel (web-frontend)

In Vercel → **Settings** → **Environment Variables**:

```bash
NEXT_PUBLIC_API_URL=https://<service>.onrender.com
```

Use the URL **without** `/api/v1` (the Next.js proxy adds it). Redeploy Vercel, then add the Vercel URL to `CORS_ORIGINS` on Render.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Web shows API offline | Check `NEXT_PUBLIC_API_URL`, Render deploy logs, and the health URL. Free-tier services sleep, so the first request can take ~1 min |
| CORS errors in browser | Add the exact Vercel production/preview URL to `CORS_ORIGINS` |
| 401 on API routes | `AUTH_DISABLED=false` needs valid Supabase env, and the user must be signed in |
| Build slow / large image | Normal (scientific Python deps such as torch) |

Railway was used before Render; the old guide is in [archive/DEPLOY-RAILWAY.md](./archive/DEPLOY-RAILWAY.md) and `railway.toml` is still in the repo.
