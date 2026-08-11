from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class ObsidianConfig:
    vault_path: Path
    notes_subdir: str


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_seconds: int


@dataclass(frozen=True)
class ProcessingConfig:
    batch_size: int
    max_retries: int
    retry_backoff_seconds: int
    store_extracted_text_in_sqlite: bool


@dataclass(frozen=True)
class AutoMoveConfig:
    enabled: bool


@dataclass(frozen=True)
class RecommendationConfig:
    default_folder: str
    default_tags: list[str]


@dataclass(frozen=True)
class BrowserScanConfig:
    enabled: bool
    interval_seconds: int


@dataclass(frozen=True)
class NotificationsConfig:
    enabled: bool
    desktop: bool
    activity_log: bool
    activity_note: bool
    print_to_console: bool
    notify_on_start: bool
    notify_on_success: bool
    notify_on_failure: bool


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    obsidian: ObsidianConfig
    ollama: OllamaConfig
    processing: ProcessingConfig
    auto_move: AutoMoveConfig
    recommendations: RecommendationConfig
    browser_scan: BrowserScanConfig
    notifications: NotificationsConfig


def load_config(path: Path) -> AppConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))

    base_dir = path.parent
    vault_path = Path(raw["obsidian"]["vault_path"])
    if not vault_path.is_absolute():
        raise ValueError("obsidian.vault_path must be an absolute path, for example D:\\Obsidian\\MyVault")

    database_raw = raw.get("database", {})
    db_path_value = database_raw.get("path")
    if db_path_value:
        db_path_text = str(db_path_value).replace("${vault}", str(vault_path))
        db_path = Path(db_path_text)
        if not db_path.is_absolute():
            db_path = base_dir / db_path
    else:
        db_path = vault_path / ".bookmark-agent" / "bookmark-agent.sqlite3"

    return AppConfig(
        database=DatabaseConfig(path=db_path),
        obsidian=ObsidianConfig(
            vault_path=vault_path,
            notes_subdir=raw["obsidian"].get("notes_subdir", "Bookmarks"),
        ),
        ollama=OllamaConfig(
            base_url=raw["ollama"].get("base_url", "http://localhost:11434").rstrip("/"),
            model=raw["ollama"].get("model", "llama3.1:8b"),
            timeout_seconds=int(raw["ollama"].get("timeout_seconds", 120)),
        ),
        processing=ProcessingConfig(
            batch_size=int(raw["processing"].get("batch_size", 5)),
            max_retries=int(raw["processing"].get("max_retries", 3)),
            retry_backoff_seconds=int(raw["processing"].get("retry_backoff_seconds", 300)),
            store_extracted_text_in_sqlite=bool(raw["processing"].get("store_extracted_text_in_sqlite", False)),
        ),
        auto_move=AutoMoveConfig(enabled=bool(raw["auto_move"].get("enabled", False))),
        recommendations=RecommendationConfig(
            default_folder=raw["recommendations"].get("default_folder", "Inbox/Bookmarks"),
            default_tags=list(raw["recommendations"].get("default_tags", ["bookmark"])),
        ),
        browser_scan=BrowserScanConfig(
            enabled=bool(raw.get("browser_scan", {}).get("enabled", True)),
            interval_seconds=int(raw.get("browser_scan", {}).get("interval_seconds", 60)),
        ),
        notifications=NotificationsConfig(
            enabled=bool(raw.get("notifications", {}).get("enabled", True)),
            desktop=bool(raw.get("notifications", {}).get("desktop", False)),
            activity_log=bool(raw.get("notifications", {}).get("activity_log", True)),
            activity_note=bool(raw.get("notifications", {}).get("activity_note", True)),
            print_to_console=bool(raw.get("notifications", {}).get("print_to_console", True)),
            notify_on_start=bool(raw.get("notifications", {}).get("notify_on_start", False)),
            notify_on_success=bool(raw.get("notifications", {}).get("notify_on_success", True)),
            notify_on_failure=bool(raw.get("notifications", {}).get("notify_on_failure", True)),
        ),
    )
