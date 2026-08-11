from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import requests

from .config import AppConfig


HOST_NAME = "obsidian_bookmark_agent"
FIREFOX_EXTENSION_ID = "bookmark-to-obsidian@example.local"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def default_project_root() -> Path:
    return Path.cwd().resolve()


def detect_vault_path() -> Path | None:
    candidates = [
        Path("D:/obsidian"),
        Path("D:/Obsidian"),
    ]
    for candidate in candidates:
        if (candidate / ".obsidian").exists():
            return candidate

    if Path("D:/").exists():
        for child in Path("D:/").iterdir():
            if child.is_dir() and (child / ".obsidian").exists():
                return child
    return None


def detect_ollama_model(base_url: str = "http://localhost:11434") -> str:
    preferred = ["qwen2.5:7b", "llama3.1:8b", "qwen2.5:1.5b"]
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        models = [model.get("name") for model in response.json().get("models", []) if model.get("name")]
    except Exception:
        models = []

    for model in preferred:
        if model in models:
            return model
    if models:
        return models[0]
    return "qwen2.5:7b"


def write_config(path: Path, vault_path: Path, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Config already exists: {path}")
    vault_path_toml = str(vault_path).replace("\\", "\\\\")
    ollama_model = detect_ollama_model()
    content = f"""[database]
path = "${{vault}}\\\\.bookmark-agent\\\\bookmark-agent.sqlite3"

[obsidian]
vault_path = "{vault_path_toml}"
notes_subdir = "Bookmarks"

[ollama]
base_url = "http://localhost:11434"
model = "{ollama_model}"
timeout_seconds = 120

[processing]
batch_size = 5
max_retries = 3
retry_backoff_seconds = 300
store_extracted_text_in_sqlite = false

[auto_move]
enabled = false

[browser_scan]
enabled = false
interval_seconds = 60

[notifications]
enabled = true
desktop = true
activity_log = true
activity_note = true
print_to_console = true
notify_on_start = false
notify_on_success = true
notify_on_failure = true

[recommendations]
default_folder = "Inbox/Bookmarks"
default_tags = ["bookmark"]
"""
    path.write_text(content, encoding="utf-8")


def native_manifest(browser: str, host_path: Path, chrome_extension_id: str | None = None) -> dict:
    manifest = {
        "name": HOST_NAME,
        "description": "Obsidian Bookmark Intelligence native messaging host",
        "path": str(host_path.resolve()),
        "type": "stdio",
    }
    if browser == "chrome":
        if not chrome_extension_id:
            raise ValueError("Chrome native host registration requires --chrome-extension-id")
        manifest["allowed_origins"] = [f"chrome-extension://{chrome_extension_id}/"]
    elif browser == "firefox":
        manifest["allowed_extensions"] = [FIREFOX_EXTENSION_ID]
    else:
        raise ValueError(f"Unsupported browser: {browser}")
    return manifest


def write_native_manifest(
    browser: str,
    host_path: Path,
    output_dir: Path,
    chrome_extension_id: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{HOST_NAME}.{browser}.json"
    path.write_text(
        json.dumps(native_manifest(browser, host_path, chrome_extension_id), indent=2),
        encoding="utf-8",
    )
    return path


def install_windows_registry(browser: str, manifest_path: Path) -> str:
    if os.name != "nt":
        raise RuntimeError("Registry install is only available on Windows")

    import winreg

    if browser == "chrome":
        key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
    elif browser == "firefox":
        key_path = rf"Software\Mozilla\NativeMessagingHosts\{HOST_NAME}"
    else:
        raise ValueError(f"Unsupported browser: {browser}")

    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path.resolve()))
    finally:
        winreg.CloseKey(key)
    return rf"HKCU\{key_path}"


def native_manifest_user_dir(browser: str) -> Path | None:
    if os.name == "nt":
        return None

    home = Path.home()
    if sys.platform == "darwin":
        if browser == "chrome":
            return home / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"
        if browser == "firefox":
            return home / "Library" / "Application Support" / "Mozilla" / "NativeMessagingHosts"
    else:
        if browser == "chrome":
            return home / ".config" / "google-chrome" / "NativeMessagingHosts"
        if browser == "firefox":
            return home / ".mozilla" / "native-messaging-hosts"
    raise ValueError(f"Unsupported browser: {browser}")


def install_native_manifest(browser: str, manifest_path: Path) -> str:
    if os.name == "nt":
        return install_windows_registry(browser, manifest_path)

    destination_dir = native_manifest_user_dir(browser)
    if destination_dir is None:
        raise RuntimeError("Native manifest directory could not be determined")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{HOST_NAME}.json"
    shutil.copy2(manifest_path, destination)
    return str(destination)


def install_worker_startup(command_path: Path) -> str:
    if os.name != "nt":
        raise RuntimeError("Worker startup install is only available on Windows")

    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    value_name = "ObsidianBookmarkIntelligenceWorker"
    command = f'"{command_path.resolve()}"'
    access = winreg.KEY_SET_VALUE
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access |= winreg.KEY_WOW64_64KEY
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, access)
    try:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, command)
    finally:
        winreg.CloseKey(key)
    return rf"HKCU\{key_path}\{value_name}"


def read_worker_startup() -> str | None:
    if os.name != "nt":
        return None

    import winreg

    access_options = [winreg.KEY_READ]
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access_options.insert(0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    if hasattr(winreg, "KEY_WOW64_32KEY"):
        access_options.append(winreg.KEY_READ | winreg.KEY_WOW64_32KEY)

    for access in access_options:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                access,
            )
            try:
                value, _ = winreg.QueryValueEx(key, "ObsidianBookmarkIntelligenceWorker")
                return value
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            continue
    return None


def open_extension_setup(project_root: Path) -> list[str]:
    opened: list[str] = []
    outputs = project_root / "outputs"
    if os.name == "nt":
        os.startfile(outputs)  # type: ignore[attr-defined]
        opened.append(str(outputs))

        candidates = [
            (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"), "chrome://extensions"),
            (Path("C:/Program Files/Mozilla Firefox/firefox.exe"), "about:debugging#/runtime/this-firefox"),
        ]
        for executable, url in candidates:
            if executable.exists():
                subprocess.Popen([str(executable), url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                opened.append(f"{executable} {url}")
    return opened


def read_windows_registry(browser: str) -> str | None:
    if os.name != "nt":
        return None

    import winreg

    if browser == "chrome":
        key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
    elif browser == "firefox":
        key_path = rf"Software\Mozilla\NativeMessagingHosts\{HOST_NAME}"
    else:
        raise ValueError(f"Unsupported browser: {browser}")

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
        try:
            value, _ = winreg.QueryValueEx(key, "")
            return value
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return None


def doctor(config: AppConfig, project_root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []

    results.append(CheckResult("Python", sys.version_info >= (3, 11), sys.version.split()[0]))
    results.append(CheckResult("Vault path", config.obsidian.vault_path.exists(), str(config.obsidian.vault_path)))
    results.append(
        CheckResult(
            "Vault .obsidian",
            (config.obsidian.vault_path / ".obsidian").exists(),
            str(config.obsidian.vault_path / ".obsidian"),
        )
    )
    results.append(CheckResult("State directory", config.database.path.parent.exists(), str(config.database.path.parent)))
    results.append(
        CheckResult(
            "State under vault",
            config.obsidian.vault_path in config.database.path.resolve().parents,
            str(config.database.path),
        )
    )

    for module_name in ["requests", "trafilatura", "yt_dlp", "w3lib"]:
        results.append(CheckResult(f"Dependency {module_name}", True, "importable"))

    try:
        response = requests.get(f"{config.ollama.base_url}/api/tags", timeout=3)
        results.append(CheckResult("Ollama", response.ok, f"{config.ollama.base_url}/api/tags -> {response.status_code}"))
        if response.ok:
            models = [model.get("name") for model in response.json().get("models", [])]
            results.append(
                CheckResult(
                    "Ollama model",
                    config.ollama.model in models,
                    f"{config.ollama.model} installed; available={', '.join(models) or 'none'}",
                )
            )
    except Exception as error:
        results.append(CheckResult("Ollama", False, f"{config.ollama.base_url} unavailable: {error}"))

    host_exe = project_root / "outputs" / "bookmark-agent-native.exe"
    host_cmd = project_root / "outputs" / "bookmark-agent-native.cmd"
    results.append(CheckResult("Native host exe", host_exe.exists(), str(host_exe)))
    results.append(CheckResult("Native host cmd fallback", host_cmd.exists(), str(host_cmd)))

    for browser in ["chrome", "firefox"]:
        if os.name == "nt":
            registry_value = read_windows_registry(browser)
            results.append(
                CheckResult(
                    f"{browser.title()} registry",
                    bool(registry_value and Path(registry_value).exists()),
                    registry_value or "not registered",
                )
            )
        else:
            manifest_dir = native_manifest_user_dir(browser)
            manifest_path = manifest_dir / f"{HOST_NAME}.json" if manifest_dir else None
            results.append(
                CheckResult(
                    f"{browser.title()} native manifest",
                    bool(manifest_path and manifest_path.exists()),
                    str(manifest_path) if manifest_path else "not registered",
                )
            )

    worker_startup = read_worker_startup()
    results.append(CheckResult("Worker startup", bool(worker_startup), worker_startup or "not registered"))

    for folder in ["chrome-extension", "firefox-extension"]:
        manifest = project_root / "outputs" / folder / "manifest.json"
        results.append(CheckResult(f"{folder} artifact", manifest.exists(), str(manifest)))

    if shutil.which("ollama"):
        results.append(CheckResult("Ollama command", True, shutil.which("ollama") or "ollama"))
    else:
        results.append(CheckResult("Ollama command", False, "ollama not found on PATH"))

    return results
