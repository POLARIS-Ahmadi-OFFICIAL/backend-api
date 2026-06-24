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
    "experiments",
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
                # key-keyed tables (app_config): upsert so latest SQLite value wins
                upsert = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT (key) DO UPDATE SET {', '.join(f'{c}=EXCLUDED.{c}' for c in cols if c != 'key')}"
            else:
                # id-keyed tables: DO NOTHING — one-time migration, skip duplicates safely
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

        # Reset sequences so Postgres autoincrement starts after the migrated data
        seq_tables = ["experiments", "conversation_events", "workflows",
                      "uploaded_files", "negative_hypotheses", "hypothesis_outcomes"]
        for tbl in seq_tables:
            pg.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {tbl}), 1))"
            ))
            print(f"  {tbl}: sequence reset")

    print("\nMigration complete. Run: DATABASE_URL=... alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
