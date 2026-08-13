from __future__ import annotations

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "obsidian-plugin"
OUTPUT = ROOT / "outputs" / "obsidian-bookmark-intelligence-plugin.zip"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    files = [SOURCE / "manifest.json", SOURCE / "main.js", SOURCE / "README.md"]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"Missing Obsidian plugin files: {', '.join(missing)}")
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    print(f"Obsidian plugin zip: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
