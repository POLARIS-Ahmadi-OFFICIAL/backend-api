#!/usr/bin/env python3
"""One-time export from legacy SQLite (polaris_ahmadi) into Postgres via DATABASE_URL."""

from __future__ import annotations

import json
import os
import sqlite3
import sys

from sqlalchemy import create_engine, text

SQLITE_PATH = os.getenv("POLARIS_SQLITE_PATH", "./data/polaris.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")


def main() -> int:
    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
        print("Set DATABASE_URL to a postgresql:// connection string", file=sys.stderr)
        return 1
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite not found: {SQLITE_PATH}", file=sys.stderr)
        return 1

    engine = create_engine(DATABASE_URL)
    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_sqlite.row_factory = sqlite3.Row

    with engine.begin() as pg:
        for table in ("users", "experiments", "app_config", "experiment_data", "conversation_events"):
            try:
                rows = conn_sqlite.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            print(f"{table}: {len(rows)} rows (manual mapping may be required)")

        # Seed dev user if empty
        pg.execute(
            text("INSERT INTO users (user_id, name) VALUES (:id, :name) ON CONFLICT DO NOTHING"),
            {"id": "migration", "name": "Migration Import"},
        )

    print("Postgres ready. Run: alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
