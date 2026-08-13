from __future__ import annotations

import json
import os
import struct
import sys

from .bookmark_import import ImportFilters, import_bookmarks
from .config import AppConfig, runtime_settings_path, save_runtime_settings
from .entitlements import current_plan, has_feature
from .service import ingest_bookmark_event
from .summarizer import DEFAULT_SUMMARY_PROMPT, prompt_path, read_summary_prompt, write_summary_prompt
from .vault_state import state_dir


def set_binary_stdio() -> None:
    if os.name != "nt":
        return
    import msvcrt

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def _read_message() -> dict | None:
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    message_length = struct.unpack("<I", raw_length)[0]
    message = sys.stdin.buffer.read(message_length)
    if not message:
        return None
    return json.loads(message.decode("utf-8"))


def _send_message(message: dict) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _recent_activity(config: AppConfig, after: str | None = None, limit: int = 20) -> dict:
    path = state_dir(config) / "activity.jsonl"
    if not path.exists():
        return {"ok": True, "command": "recent-activity", "entries": []}

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = entry.get("timestamp") or ""
            if after and timestamp <= after:
                continue
            entries.append(entry)

    return {
        "ok": True,
        "command": "recent-activity",
        "entries": entries[-max(1, min(limit, 100)) :],
    }


def _handle_control_message(config: AppConfig, message: dict) -> dict | None:
    command = message.get("command")
    if command == "get-agent-settings":
        return {
            "ok": True,
            "command": command,
            "vault_path": str(config.obsidian.vault_path),
            "database_path": str(config.database.path),
            "notes_subdir": config.obsidian.notes_subdir,
            "provider": config.summarizer.provider,
            "model": config.summarizer.model,
            "base_url": config.summarizer.base_url,
            "api_key_env": config.summarizer.api_key_env,
            "runtime_settings_path": str(runtime_settings_path(config.obsidian.vault_path)),
            "plan": current_plan(config),
            "support_links": config.support.links,
            "summary_prompt": read_summary_prompt(config),
            "default_summary_prompt": DEFAULT_SUMMARY_PROMPT,
            "summary_prompt_path": str(prompt_path(config)),
        }

    if command == "save-agent-settings":
        prompt = message.get("summary_prompt")
        if prompt is not None:
            if not isinstance(prompt, str):
                return {"ok": False, "error": "summary_prompt must be a string"}
            write_summary_prompt(config, prompt)
        runtime_fields = {key: message[key] for key in ("provider", "model", "base_url", "api_key_env") if key in message}
        settings_path = None
        if runtime_fields:
            if not all(isinstance(value, str) for value in runtime_fields.values()):
                return {"ok": False, "error": "AI settings must be strings"}
            settings_path = save_runtime_settings(
                config.obsidian.vault_path,
                {
                    "provider": config.summarizer.provider,
                    "model": config.summarizer.model,
                    "base_url": config.summarizer.base_url,
                    "api_key_env": config.summarizer.api_key_env,
                    **runtime_fields,
                },
            )
        return {
            "ok": True,
            "command": command,
            "summary_prompt_path": str(prompt_path(config)),
            "runtime_settings_path": str(settings_path or runtime_settings_path(config.obsidian.vault_path)),
        }

    if command == "import-bookmarks":
        if not has_feature(config, "bulk_analysis"):
            return {"ok": False, "error": "Existing bookmark bulk analysis is a Pro feature."}
        mode = message.get("mode") or "summarize"
        filters = ImportFilters(
            browser=message.get("browser"),
            profile=message.get("profile"),
            folder=message.get("folder"),
            domain=message.get("domain"),
            url_contains=message.get("url_contains"),
            resource_type=message.get("resource_type"),
            limit=message.get("limit"),
        )
        result = import_bookmarks(config, mode, filters, dry_run=bool(message.get("dry_run")))
        result["command"] = command
        return result

    if command == "recent-activity":
        return _recent_activity(
            config,
            after=message.get("after"),
            limit=int(message.get("limit") or 20),
        )

    if command != "ping":
        return None
    return {
        "ok": True,
        "command": "ping",
        "vault_path": str(config.obsidian.vault_path),
        "database_path": str(config.database.path),
        "notes_subdir": config.obsidian.notes_subdir,
        "provider": config.summarizer.provider,
        "model": config.summarizer.model,
        "plan": current_plan(config),
        "support_links": config.support.links,
    }


def run_native_host(config: AppConfig) -> None:
    set_binary_stdio()
    while True:
        message = _read_message()
        if message is None:
            return
        try:
            result = _handle_control_message(config, message)
            if result is None:
                result = ingest_bookmark_event(config, message)
            _send_message(result)
        except Exception as error:
            _send_message({"ok": False, "error": str(error)})
