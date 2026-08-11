from __future__ import annotations

import json

from .canonical import canonicalize_url, resource_type_for_url
from .database import transaction, utc_now
from .config import AppConfig
from .vault_state import append_event_log, write_last_result


def ingest_bookmark_event(config: AppConfig, payload: dict) -> dict:
    source = payload.get("source") or {}
    event = payload.get("event") or {}
    bookmark = payload.get("bookmark") or {}

    browser = source.get("browser") or "unknown"
    profile_id = source.get("profile_id") or source.get("profile") or "default"
    event_type = event.get("type") or "unknown"
    bookmark_id = bookmark.get("id")
    title = bookmark.get("title") or ""
    url = bookmark.get("url")
    parent_id = bookmark.get("parentId")
    received_at = utc_now()

    resource_id = None
    resource_type = None
    process_status = None
    canonical_url = canonicalize_url(url) if url else None
    status = "removed" if event_type == "removed" else "active"

    with transaction(config.database.path) as connection:
        connection.execute(
            """
            INSERT INTO bookmark_events (received_at, browser, profile_id, event_type, bookmark_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                received_at,
                browser,
                profile_id,
                event_type,
                bookmark_id,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )

        if bookmark_id:
            connection.execute(
                """
                INSERT INTO bookmarks (
                  browser, profile_id, bookmark_id, url, canonical_url, title, parent_id, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(browser, profile_id, bookmark_id) DO UPDATE SET
                  url = excluded.url,
                  canonical_url = excluded.canonical_url,
                  title = excluded.title,
                  parent_id = excluded.parent_id,
                  status = excluded.status,
                  updated_at = excluded.updated_at
                """,
                (browser, profile_id, bookmark_id, url, canonical_url, title, parent_id, status, received_at),
            )

        if url and event_type != "removed" and canonical_url:
            resource_type = resource_type_for_url(canonical_url)
            connection.execute(
                """
                INSERT INTO resources (canonical_url, url, resource_type, title, process_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                  url = excluded.url,
                  title = COALESCE(NULLIF(excluded.title, ''), resources.title),
                  updated_at = excluded.updated_at,
                  process_status = CASE
                    WHEN resources.process_status = 'succeeded' THEN resources.process_status
                    ELSE 'pending'
                  END
                """,
                (canonical_url, url, resource_type, title, received_at, received_at),
            )
            resource_row = connection.execute(
                "SELECT id, process_status, resource_type FROM resources WHERE canonical_url = ?",
                (canonical_url,),
            ).fetchone()
            resource_id = resource_row["id"]
            process_status = resource_row["process_status"]
            resource_type = resource_row["resource_type"]

    result = {
        "ok": True,
        "event_type": event_type,
        "browser": browser,
        "profile_id": profile_id,
        "bookmark_id": bookmark_id,
        "canonical_url": canonical_url,
        "resource_type": resource_type,
        "process_status": process_status,
        "resource_id": resource_id,
    }
    append_event_log(config, payload, result)
    write_last_result(config, result)
    return result
