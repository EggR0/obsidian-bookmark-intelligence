from __future__ import annotations

from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import hashlib
import json
import os
import time

from .browser_scan import scan_browser_bookmarks
from .config import AppConfig
from .database import transaction, utc_now
from .extraction import extract_resource
from .markdown import write_obsidian_note
from .recommendations import derive_recommendations
from .summarizer import summarize_with_ollama
from .vault_state import state_dir


@contextmanager
def worker_lock(config: AppConfig):
    lock_path = state_dir(config) / "worker.lock"
    lock_file = lock_path.open("a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                raise RuntimeError(f"Another worker is already running for this vault: {config.obsidian.vault_path}")
        else:
            import fcntl

            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                raise RuntimeError(f"Another worker is already running for this vault: {config.obsidian.vault_path}")
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def _now_for_sql() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_due_resources(config: AppConfig) -> list[dict]:
    now = _now_for_sql()
    with transaction(config.database.path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM resources
            WHERE process_status = 'pending'
               OR (process_status = 'failed' AND retry_count < ? AND (next_retry_at IS NULL OR next_retry_at <= ?))
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (config.processing.max_retries, now, config.processing.batch_size),
        ).fetchall()

        resource_ids = [row["id"] for row in rows]
        if resource_ids:
            placeholders = ",".join("?" for _ in resource_ids)
            connection.execute(
                f"UPDATE resources SET process_status = 'processing', updated_at = ? WHERE id IN ({placeholders})",
                (now, *resource_ids),
            )
        return [dict(row) for row in rows]


def process_resource(config: AppConfig, resource: dict) -> None:
    extracted = extract_resource(resource["url"], resource["resource_type"])
    content_hash = hashlib.sha256(extracted.text.encode("utf-8")).hexdigest()
    summary = summarize_with_ollama(config, extracted.title, resource["url"], extracted.text)
    recommended_folder, recommended_tags = derive_recommendations(config, summary)
    markdown_path = write_obsidian_note(
        config,
        title=extracted.title or resource["title"] or resource["url"],
        url=resource["url"],
        canonical_url=resource["canonical_url"],
        resource_type=resource["resource_type"],
        summary=summary,
        recommended_folder=recommended_folder,
        recommended_tags=recommended_tags,
    )

    now = utc_now()
    with transaction(config.database.path) as connection:
        connection.execute(
            """
            UPDATE resources
            SET process_status = 'succeeded',
                title = ?,
                content_hash = ?,
                markdown_path = ?,
                last_error = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (extracted.title, content_hash, str(markdown_path), now, resource["id"]),
        )
        connection.execute(
            """
            INSERT INTO resource_metadata (
              resource_id, metadata_json, summary, recommended_folder, recommended_tags_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_id) DO UPDATE SET
              metadata_json = excluded.metadata_json,
              summary = excluded.summary,
              recommended_folder = excluded.recommended_folder,
              recommended_tags_json = excluded.recommended_tags_json,
              updated_at = excluded.updated_at
            """,
            (
                resource["id"],
                json.dumps(extracted.metadata, ensure_ascii=False),
                summary,
                recommended_folder,
                json.dumps(recommended_tags, ensure_ascii=False),
                now,
            ),
        )


def mark_failed(config: AppConfig, resource: dict, error: Exception) -> None:
    retry_count = int(resource["retry_count"]) + 1
    next_retry = datetime.now(UTC) + timedelta(seconds=config.processing.retry_backoff_seconds * retry_count)
    with transaction(config.database.path) as connection:
        connection.execute(
            """
            UPDATE resources
            SET process_status = 'failed',
                retry_count = ?,
                next_retry_at = ?,
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                retry_count,
                next_retry.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                str(error)[:1000],
                utc_now(),
                resource["id"],
            ),
        )


def run_worker(config: AppConfig, once: bool = False, sleep_seconds: int = 10) -> None:
    with worker_lock(config):
        last_scan_at = 0.0
        while True:
            now_monotonic = time.monotonic()
            if config.browser_scan.enabled and (
                once or now_monotonic - last_scan_at >= config.browser_scan.interval_seconds
            ):
                try:
                    scan_browser_bookmarks(config)
                except Exception:
                    pass
                last_scan_at = now_monotonic

            resources = fetch_due_resources(config)
            for resource in resources:
                try:
                    process_resource(config, resource)
                except Exception as error:
                    mark_failed(config, resource, error)

            if once:
                return
            time.sleep(sleep_seconds)
