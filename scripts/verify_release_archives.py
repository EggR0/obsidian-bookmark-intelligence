from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile


FORBIDDEN_PARTS = ("__pycache__", ".venv", "work", "data")
FORBIDDEN_SUFFIXES = (".pyc",)
FORBIDDEN_NAMES = {"bookmark-agent.sqlite3", "config.toml"}


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
