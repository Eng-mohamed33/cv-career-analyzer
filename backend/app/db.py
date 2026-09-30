import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATABASE_PATH = Path(os.getenv("DATABASE_PATH") or Path(__file__).resolve().parent.parent / "careerai.db")


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    with get_db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username TEXT PRIMARY KEY, display_name TEXT NOT NULL, password_hash TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS cvs ("
            "id TEXT PRIMARY KEY, user_id TEXT, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL, "
            "score INTEGER NOT NULL, analysis_json TEXT NOT NULL)"
        )
        # Migration: databases created before auth existed have no user_id column.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(cvs)")}
        if "user_id" not in columns:
            db.execute("ALTER TABLE cvs ADD COLUMN user_id TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_cvs_user ON cvs (user_id, uploaded_at DESC)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS job_matches ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, cv_id TEXT NOT NULL, user_id TEXT NOT NULL, "
            "result_json TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_matches_cv ON job_matches (cv_id, id DESC)")
