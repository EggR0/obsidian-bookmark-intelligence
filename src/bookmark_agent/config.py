from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class ObsidianConfig:
    vault_path: Path
    notes_subdir: str


@dataclass(frozen=True)
class SummarizerConfig:
    provider: str
    base_url: str
    model: str
    api_key_env: str
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
class FeaturesConfig:
    pro_enabled: bool


@dataclass(frozen=True)
class SupportConfig:
    links: dict[str, str]


@dataclass(frozen=True)
class EntitlementConfig:
    endpoint: str
    account_id: str
    access_token_env: str
    timeout_seconds: int


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    obsidian: ObsidianConfig
    summarizer: SummarizerConfig
    processing: ProcessingConfig
    auto_move: AutoMoveConfig
    recommendations: RecommendationConfig
    browser_scan: BrowserScanConfig
    notifications: NotificationsConfig
    features: FeaturesConfig
    support: SupportConfig
    entitlements: EntitlementConfig

    @property
    def ollama(self) -> SummarizerConfig:
        """Compatibility alias for older extension and diagnostic code."""
        return self.summarizer


def default_state_dir(vault_path: Path) -> Path:
    identity = hashlib.sha256(str(vault_path.resolve()).encode("utf-8")).hexdigest()[:16]
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif os.sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "Bookmark Intelligence" / identity


def runtime_settings_path(vault_path: Path) -> Path:
    return default_state_dir(vault_path) / "agent-settings.json"


def _read_runtime_settings(vault_path: Path) -> dict[str, str]:
    path = runtime_settings_path(vault_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    settings = {key: str(value).strip() for key, value in payload.items() if isinstance(value, str)}
    if settings.get("provider") not in {"ollama", "openai", "gemini", "anthropic", "hosted"}:
        return {}
    if not settings.get("model") or not settings.get("base_url", "").startswith(("http://", "https://")):
        return {}
    return settings


def save_runtime_settings(vault_path: Path, settings: dict[str, str]) -> Path:
    allowed = {"provider", "model", "base_url", "api_key_env", "entitlement_endpoint", "account_id", "access_token_env"}
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"Unsupported runtime settings: {', '.join(sorted(unknown))}")
    provider = settings.get("provider", "").lower()
    if provider not in {"ollama", "openai", "gemini", "anthropic", "hosted"}:
        raise ValueError("Unsupported AI provider")
    model = settings.get("model", "").strip()
    if not model or len(model) > 200:
        raise ValueError("AI model must be between 1 and 200 characters")
    base_url = settings.get("base_url", "").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("AI base URL must start with http:// or https://")
    api_key_env = settings.get("api_key_env", "").strip()
    if api_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", api_key_env):
        raise ValueError("API key environment variable name is invalid")
    entitlement_endpoint = settings.get("entitlement_endpoint", "").strip().rstrip("/")
    if entitlement_endpoint and not entitlement_endpoint.startswith(("http://", "https://")):
        raise ValueError("Entitlement endpoint must start with http:// or https://")
    account_id = settings.get("account_id", "").strip()
    access_token_env = settings.get("access_token_env", "").strip()
    if access_token_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", access_token_env):
        raise ValueError("Access token environment variable name is invalid")
    path = runtime_settings_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key_env": api_key_env,
                "entitlement_endpoint": entitlement_endpoint,
                "account_id": account_id,
                "access_token_env": access_token_env,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


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
        db_path_text = db_path_text.replace("${state}", str(default_state_dir(vault_path)))
        db_path = Path(db_path_text)
        if ".bookmark-agent" in db_path.parts:
            db_path = default_state_dir(vault_path) / db_path.name
        if not db_path.is_absolute():
            db_path = base_dir / db_path
    else:
        db_path = default_state_dir(vault_path) / "bookmark-agent.sqlite3"

    summarizer_raw = raw.get("summarizer") or raw.get("ollama", {})
    provider = str(summarizer_raw.get("provider", "ollama")).lower()
    default_endpoint = {
        "ollama": "http://localhost:11434",
        "openai": "https://api.openai.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
        "anthropic": "https://api.anthropic.com/v1",
        "hosted": "http://127.0.0.1:8788",
    }.get(provider, "http://localhost:11434")

    config = AppConfig(
        database=DatabaseConfig(path=db_path),
        obsidian=ObsidianConfig(
            vault_path=vault_path,
            notes_subdir=raw["obsidian"].get("notes_subdir", "Bookmarks"),
        ),
        summarizer=SummarizerConfig(
            provider=provider,
            base_url=str(summarizer_raw.get("base_url", default_endpoint)).rstrip("/"),
            model=str(summarizer_raw.get("model", "qwen2.5:7b" if provider == "ollama" else "gpt-5.4-nano")),
            api_key_env=str(summarizer_raw.get("api_key_env", "")),
            timeout_seconds=int(summarizer_raw.get("timeout_seconds", 120)),
        ),
        processing=ProcessingConfig(
            batch_size=int(raw["processing"].get("batch_size", 5)),
            max_retries=int(raw["processing"].get("max_retries", 3)),
            retry_backoff_seconds=int(raw["processing"].get("retry_backoff_seconds", 300)),
            store_extracted_text_in_sqlite=bool(raw["processing"].get("store_extracted_text_in_sqlite", False)),
        ),
        auto_move=AutoMoveConfig(enabled=bool(raw.get("auto_move", {}).get("enabled", False))),
        recommendations=RecommendationConfig(
            default_folder=raw.get("recommendations", {}).get("default_folder", "Inbox/Bookmarks"),
            default_tags=list(raw.get("recommendations", {}).get("default_tags", ["bookmark"])),
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
        features=FeaturesConfig(pro_enabled=bool(raw.get("features", {}).get("pro_enabled", False))),
        support=SupportConfig(
            links={
                key: str(value).strip()
                for key, value in raw.get("support", {}).items()
                if isinstance(value, str) and value.strip()
            }
        ),
        entitlements=EntitlementConfig(
            endpoint=str(raw.get("entitlements", {}).get("endpoint", "")).strip().rstrip("/"),
            account_id=str(raw.get("entitlements", {}).get("account_id", "")).strip(),
            access_token_env=str(raw.get("entitlements", {}).get("access_token_env", "")).strip(),
            timeout_seconds=int(raw.get("entitlements", {}).get("timeout_seconds", 10)),
        ),
    )

    runtime = _read_runtime_settings(vault_path)
    if runtime:
        config = replace(
            config,
            summarizer=replace(
                config.summarizer,
                provider=runtime.get("provider", config.summarizer.provider),
                base_url=runtime.get("base_url", config.summarizer.base_url),
                model=runtime.get("model", config.summarizer.model),
                api_key_env=runtime.get("api_key_env", config.summarizer.api_key_env),
            ),
            entitlements=replace(
                config.entitlements,
                endpoint=runtime.get("entitlement_endpoint", config.entitlements.endpoint),
                account_id=runtime.get("account_id", config.entitlements.account_id),
                access_token_env=runtime.get("access_token_env", config.entitlements.access_token_env),
            ),
        )
    return config
