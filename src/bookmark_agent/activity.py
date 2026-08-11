from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys

from .config import AppConfig
from .vault_state import state_dir


APP_NAME = "Obsidian Bookmark Intelligence"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shorten(text: str, limit: int = 160) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _activity_log_path(config: AppConfig) -> Path:
    return state_dir(config) / "activity.jsonl"


def _activity_note_path(config: AppConfig) -> Path:
    return config.obsidian.vault_path / config.obsidian.notes_subdir / "_Activity.md"


def _append_jsonl(config: AppConfig, entry: dict) -> None:
    path = _activity_log_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _append_activity_note(config: AppConfig, entry: dict) -> None:
    path = _activity_note_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Bookmark Agent Activity\n\n", encoding="utf-8")

    title = entry.get("title") or entry.get("resource_title") or "Bookmark Agent"
    message = entry.get("message") or ""
    resource_url = entry.get("resource_url") or ""
    model = entry.get("ollama_model") or ""
    status = entry.get("event_type") or "event"
    lines = [
        f"## {entry['timestamp']} - {status}",
        "",
        f"- Title: {title}",
        f"- Message: {message}",
    ]
    if resource_url:
        lines.append(f"- URL: {resource_url}")
    if model:
        lines.append(f"- Ollama model: {model}")
    if entry.get("markdown_path"):
        lines.append(f"- Markdown: {entry['markdown_path']}")
    if entry.get("error"):
        lines.append(f"- Error: {entry['error']}")
    lines.append("")

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _print_console(entry: dict) -> None:
    message = entry.get("message") or ""
    title = entry.get("title") or entry.get("resource_title") or APP_NAME
    print(f"[{entry['timestamp']}] {entry['event_type']}: {title} - {message}", flush=True)


def _send_windows_notification(title: str, message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        from winotify import Notification

        toast = Notification(app_id=APP_NAME, title=_shorten(title, 64), msg=_shorten(message, 220))
        toast.show()
    except Exception:
        return


def record_activity(
    config: AppConfig,
    event_type: str,
    title: str,
    message: str,
    *,
    resource: dict | None = None,
    details: dict | None = None,
    notify: bool = False,
) -> None:
    if not config.notifications.enabled:
        return

    details = details or {}
    resource = resource or {}
    entry = {
        "timestamp": _utc_now(),
        "event_type": event_type,
        "title": title,
        "message": message,
        "resource_id": resource.get("id"),
        "resource_title": resource.get("title"),
        "resource_url": resource.get("url"),
        "canonical_url": resource.get("canonical_url"),
        "resource_type": resource.get("resource_type"),
        **details,
    }

    if config.notifications.activity_log:
        _append_jsonl(config, entry)
    if config.notifications.activity_note:
        _append_activity_note(config, entry)
    if config.notifications.print_to_console:
        _print_console(entry)
    if notify and config.notifications.desktop:
        _send_windows_notification(title, message)
