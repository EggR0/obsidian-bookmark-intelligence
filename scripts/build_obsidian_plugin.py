from __future__ import annotations

from pathlib import Path
import zipfile
import json


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "obsidian-plugin"
OUTPUT = ROOT / "outputs" / "obsidian-bookmark-intelligence-plugin.zip"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    files = [SOURCE / "manifest.json", SOURCE / "main.js", SOURCE / "README.md", SOURCE / "versions.json"]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"Missing Obsidian plugin files: {', '.join(missing)}")
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    versions = json.loads((SOURCE / "versions.json").read_text(encoding="utf-8"))
    if manifest["version"] not in versions:
        raise SystemExit("versions.json does not contain the manifest version")
    if versions[manifest["version"]] != manifest["minAppVersion"]:
        raise SystemExit("versions.json minAppVersion does not match manifest.json")
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    print(f"Obsidian plugin zip: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
