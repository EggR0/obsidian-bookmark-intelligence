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
  profile_id TEXT NOT NULL DEFAULT 'default',
  event_type TEXT NOT NULL,
  bookmark_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmarks (
  browser TEXT NOT NULL,
  profile_id TEXT NOT NULL DEFAULT 'default',
  bookmark_id TEXT NOT NULL,
  url TEXT,
  canonical_url TEXT,
  title TEXT,
  parent_id TEXT,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (browser, profile_id, bookmark_id)
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
        _migrate_profile_columns(connection)
        connection.commit()
    finally:
        connection.close()


def _table_columns(connection: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _primary_key_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [row["name"] for row in sorted((row for row in rows if row["pk"]), key=lambda row: row["pk"])]


def _migrate_profile_columns(connection: sqlite3.Connection) -> None:
    event_columns = _table_columns(connection, "bookmark_events")
    if "profile_id" not in event_columns:
        connection.execute("ALTER TABLE bookmark_events ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'default'")

    bookmark_pk = _primary_key_columns(connection, "bookmarks")
    if bookmark_pk == ["browser", "profile_id", "bookmark_id"]:
        return

    connection.execute("ALTER TABLE bookmarks RENAME TO bookmarks_legacy_profile_migration")
    connection.execute(
        """
        CREATE TABLE bookmarks (
          browser TEXT NOT NULL,
          profile_id TEXT NOT NULL DEFAULT 'default',
          bookmark_id TEXT NOT NULL,
          url TEXT,
          canonical_url TEXT,
          title TEXT,
          parent_id TEXT,
          status TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (browser, profile_id, bookmark_id)
        )
        """
    )

    legacy_columns = _table_columns(connection, "bookmarks_legacy_profile_migration")
    profile_expr = "COALESCE(profile_id, 'default')" if "profile_id" in legacy_columns else "'default'"
    connection.execute(
        f"""
        INSERT OR REPLACE INTO bookmarks (
          browser, profile_id, bookmark_id, url, canonical_url, title, parent_id, status, updated_at
        )
        SELECT
          browser,
          {profile_expr},
          bookmark_id,
          url,
          canonical_url,
          title,
          parent_id,
          status,
          updated_at
        FROM bookmarks_legacy_profile_migration
        """
    )
    connection.execute("DROP TABLE bookmarks_legacy_profile_migration")


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
