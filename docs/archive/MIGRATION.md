# Migration from polaris_ahmadi

Source repository: https://github.com/CyberA183/polaris_ahmadi

| Source | Destination |
|--------|-------------|
| `agents/` | `app/agents/` |
| `tools/` | `app/tools/` |
| `watcher/` | `app/watcher/` |
| `tests/test_*.py` | `tests/` |
| `init_db.py` | `init_db.py` |
| Streamlit `pages/` | `web-frontend/app/(app)/` (UI only) |

Streamlit UI and Briefcase packaging are not ported. API contract: `@polaris/shared-types` OpenAPI v1.
