from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile


FORBIDDEN_PARTS = ("__pycache__", ".venv", "work", "data")
FORBIDDEN_SUFFIXES = (".pyc",)
FORBIDDEN_NAMES = {"bookmark-agent.sqlite3", "config.toml"}
EXTENSION_FILES = {"background.js", "manifest.json", "options.html", "options.js", "popup.html", "popup.js"}


def verify_archive(path: Path, expected_version: str) -> None:
    with ZipFile(path) as archive:
        names = archive.namelist()
        bad = [
            name
            for name in names
            if any(part in name.lower().split("/") for part in FORBIDDEN_PARTS)
            or name.lower().endswith(FORBIDDEN_SUFFIXES)
            or Path(name).name.lower() in FORBIDDEN_NAMES
        ]
        if bad:
            raise ValueError(f"{path} contains forbidden release files: {', '.join(bad[:5])}")

        manifest_names = [name for name in names if Path(name).name == "manifest.json"]
        for name in manifest_names:
            content = archive.read(name).decode("utf-8")
            marker = f'"version": "{expected_version}"'
            if marker not in content:
                raise ValueError(f"{path}:{name} does not contain version {expected_version}")

        if path.name in {"chrome-extension.zip", "firefox-extension.xpi"}:
            _verify_extension_archive(path, archive, names, expected_version)


def _verify_extension_archive(path: Path, archive: ZipFile, names: list[str], expected_version: str) -> None:
    required = EXTENSION_FILES | {"icon16.png", "icon48.png", "icon128.png"}
    missing = sorted(required - set(names))
    if missing:
        raise ValueError(f"{path} is missing extension files: {', '.join(missing)}")
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} has an invalid root manifest.json") from error
    if manifest.get("version") != expected_version:
        raise ValueError(f"{path} manifest version is not {expected_version}")
    if path.name == "firefox-extension.xpi":
        extension_id = manifest.get("browser_specific_settings", {}).get("gecko", {}).get("id")
        if extension_id != "bookmark-intelligence@eggr0.github.io":
            raise ValueError(f"{path} has an unexpected Firefox extension id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Bookmark Intelligence release archives")
    parser.add_argument("--version", required=True)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    version = args.version.removeprefix("v")
    for archive in args.archives:
        verify_archive(archive, version)
        print(f"verified: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
