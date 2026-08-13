from __future__ import annotations

import json

from .config import AppConfig, default_state_dir
from .database import utc_now


def state_dir(config: AppConfig):
    path = default_state_dir(config.obsidian.vault_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_event_log(config: AppConfig, payload: dict, ingest_result: dict) -> None:
    entry = {
        "logged_at": utc_now(),
        "event": payload.get("event", {}),
        "source": payload.get("source", {}),
        "bookmark": payload.get("bookmark", {}),
        "canonical_url": ingest_result.get("canonical_url"),
        "resource_id": ingest_result.get("resource_id"),
        "profile_id": ingest_result.get("profile_id") or (payload.get("source") or {}).get("profile_id"),
    }
    path = state_dir(config) / "events.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_last_result(config: AppConfig, result: dict) -> None:
    path = state_dir(config) / "last-result.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
