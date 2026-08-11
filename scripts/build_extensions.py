from __future__ import annotations

from pathlib import Path
from base64 import b64decode
import hashlib
import json
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_SRC = ROOT / "extension"
OUTPUTS = ROOT / "outputs"


def copy_extension(target: Path, manifest_name: str) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    for filename in [
        "background.js",
        "popup.html",
        "popup.css",
        "popup.js",
        "options.html",
        "options.css",
        "options.js",
        "icon.svg",
        "icon16.png",
        "icon48.png",
        "icon128.png",
    ]:
        shutil.copy2(EXTENSION_SRC / filename, target / filename)
    shutil.copy2(EXTENSION_SRC / manifest_name, target / "manifest.json")


def chrome_extension_id_from_key(manifest_path: Path) -> str | None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = manifest.get("key")
    if not key:
        return None
    digest = hashlib.sha256(b64decode(key)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def zip_dir(source: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source))


def main() -> int:
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    chrome_dir = OUTPUTS / "chrome-extension"
    firefox_dir = OUTPUTS / "firefox-extension"

    copy_extension(chrome_dir, "manifest.chrome.json")
    copy_extension(firefox_dir, "manifest.firefox.json")

    zip_dir(chrome_dir, OUTPUTS / "chrome-extension.zip")
    zip_dir(firefox_dir, OUTPUTS / "firefox-extension.zip")
    shutil.copy2(OUTPUTS / "firefox-extension.zip", OUTPUTS / "firefox-extension.xpi")

    chrome_extension_id = chrome_extension_id_from_key(chrome_dir / "manifest.json")
    if chrome_extension_id:
        (OUTPUTS / "chrome-extension-key-derived-id.txt").write_text(chrome_extension_id + "\n", encoding="utf-8")

    print(f"Chrome unpacked: {chrome_dir}")
    print(f"Chrome zip:      {OUTPUTS / 'chrome-extension.zip'}")
    if chrome_extension_id:
        print(f"Chrome key ID:   {chrome_extension_id}")
    print(f"Firefox unpacked:{firefox_dir}")
    print(f"Firefox zip:     {OUTPUTS / 'firefox-extension.zip'}")
    print(f"Firefox xpi:     {OUTPUTS / 'firefox-extension.xpi'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
