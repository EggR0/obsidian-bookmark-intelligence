from __future__ import annotations

import json
import os
import struct
import sys

from .bookmark_import import ImportFilters, import_bookmarks
from .config import AppConfig
from .service import ingest_bookmark_event


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


def _handle_control_message(config: AppConfig, message: dict) -> dict | None:
    command = message.get("command")
    if command == "import-bookmarks":
        mode = message.get("mode") or "index"
        if mode != "index":
            return {"ok": False, "error": "Native import currently supports index mode only."}
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

    if command != "ping":
        return None
    return {
        "ok": True,
        "command": "ping",
        "vault_path": str(config.obsidian.vault_path),
        "database_path": str(config.database.path),
        "notes_subdir": config.obsidian.notes_subdir,
        "ollama_model": config.ollama.model,
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
