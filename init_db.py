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
    # Load .env so POLARIS_DB_PATH is picked up
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(_root, ".env"))
    except ImportError:
        pass


def init_database() -> str:
    """
    Create the database file, tables, and default values.
    Returns the path to the database file.
    """
    from app.tools.database import DatabaseManager
    from app.tools.paths import get_db_path, get_user_data_dir

    db_path = get_db_path()
    user_dir = get_user_data_dir()

    db = DatabaseManager()
    db.init_schema()
    db.ensure_defaults()

    return db_path


if __name__ == "__main__":
    try:
        path = init_database()
        shared = " (shared)" if os.environ.get("POLARIS_DB_PATH") else ""
        print(f"Database initialized{shared}: {path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
