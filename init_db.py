#!/usr/bin/env python3
"""
Standalone database initializer for Polaris Ahmadi.
Creates the database and schema without starting Streamlit or any other app.

Run before your app starts:
    python init_db.py

Or from another directory:
    python -m init_db

Or import and call:
    from init_db import init_database
    init_database()
"""

import os
import sys

# Ensure project root is in path when run as script
if __name__ == "__main__":
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    # Load .env so DATABASE_URL is picked up
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_root, ".env"))
    except ImportError:
        pass


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
        # Seed default rows (idempotent — checks before inserting)
        from app.tools.database import DatabaseManager
        DatabaseManager().ensure_defaults()
        return "postgres"
    else:
        from app.tools.database import DatabaseManager
        db = DatabaseManager()
        db.init_schema()
        db.ensure_defaults()
        db_path = url.replace("sqlite+aiosqlite:///", "")
        return db_path


if __name__ == "__main__":
    try:
        result = init_database()
        print(f"Database initialized: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
