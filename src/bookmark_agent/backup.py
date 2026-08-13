from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from .config import AppConfig, default_state_dir
from .database import init_db


ARCHIVE_VERSION = 1
STATE_FILES = ("events.jsonl", "activity.jsonl", "last-result.json", "summary-prompt.txt")


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _vault_id(config: AppConfig) -> str:
    return default_state_dir(config.obsidian.vault_path).name


def _manifest(config: AppConfig) -> dict:
    return {
        "format": "bookmark-intelligence-state",
        "version": ARCHIVE_VERSION,
        "created_at": _timestamp(),
        "vault_id": _vault_id(config),
        "notes_excluded": True,
        "api_keys_excluded": True,
        "raw_sources_excluded": True,
    }


def backup_state(config: AppConfig, destination: Path) -> dict:
    """Create a Pro state backup without copying Vault notes or secrets."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    state = default_state_dir(config.obsidian.vault_path)
    state.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bookmark-intelligence-backup-") as temporary:
        temporary_db = Path(temporary) / "bookmark-agent.sqlite3"
        init_db(config.database.path)
        source = sqlite3.connect(config.database.path)
        target = sqlite3.connect(temporary_db)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

        manifest = _manifest(config)
        with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.write(temporary_db, "bookmark-agent.sqlite3")
            for name in STATE_FILES:
                path = state / name
                if path.is_file():
                    archive.write(path, name)

    return {"ok": True, "path": str(destination), "manifest": manifest}


def restore_state(config: AppConfig, archive_path: Path) -> dict:
    """Restore only approved app-state files into this Vault's state directory."""
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Backup archive does not exist: {archive_path}")

    with ZipFile(archive_path) as archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            archive.getinfo("bookmark-agent.sqlite3")
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Invalid Bookmark Intelligence backup archive") from error

        if manifest.get("format") != "bookmark-intelligence-state" or manifest.get("version") != ARCHIVE_VERSION:
            raise ValueError("Unsupported Bookmark Intelligence backup format")
        if manifest.get("vault_id") != _vault_id(config):
            raise ValueError("This backup belongs to a different Obsidian Vault")
        if not manifest.get("notes_excluded") or not manifest.get("api_keys_excluded"):
            raise ValueError("Backup does not satisfy the no-notes/no-secrets policy")

        state = default_state_dir(config.obsidian.vault_path)
        state.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bookmark-intelligence-restore-") as temporary:
            temporary_db = Path(temporary) / "bookmark-agent.sqlite3"
            temporary_db.write_bytes(archive.read("bookmark-agent.sqlite3"))
            source = sqlite3.connect(temporary_db)
            target = sqlite3.connect(config.database.path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()

            restored = ["bookmark-agent.sqlite3"]
            for name in STATE_FILES:
                if name not in archive.namelist():
                    continue
                target_path = state / name
                target_path.write_bytes(archive.read(name))
                restored.append(name)

    return {"ok": True, "path": str(archive_path), "restored": restored, "vault_id": _vault_id(config)}
