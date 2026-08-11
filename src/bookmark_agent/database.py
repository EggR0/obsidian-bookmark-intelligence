from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3


SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS bookmark_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT NOT NULL,
  browser TEXT NOT NULL,
  event_type TEXT NOT NULL,
  bookmark_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmarks (
  browser TEXT NOT NULL,
  bookmark_id TEXT NOT NULL,
  url TEXT,
  canonical_url TEXT,
  title TEXT,
  parent_id TEXT,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (browser, bookmark_id)
);

CREATE TABLE IF NOT EXISTS resources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_url TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  title TEXT,
  process_status TEXT NOT NULL DEFAULT 'pending',
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,
  last_error TEXT,
  content_hash TEXT,
  markdown_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_metadata (
  resource_id INTEGER PRIMARY KEY,
  metadata_json TEXT NOT NULL,
  summary TEXT,
  recommended_folder TEXT,
  recommended_tags_json TEXT,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(resource_id) REFERENCES resources(id)
);

CREATE INDEX IF NOT EXISTS idx_resources_process
ON resources(process_status, next_retry_at, updated_at);
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path) -> None:
    connection = connect(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


@contextmanager
def transaction(db_path: Path):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
