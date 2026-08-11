from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "outputs" / "chrome-extension"
OUTPUT_PATH = ROOT / "outputs" / "chrome-extension-id.txt"
EXPECTED_ID_PATH = ROOT / "outputs" / "chrome-extension-key-derived-id.txt"
CHROME_CANDIDATES = [
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
]


def find_chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find chrome.exe")


def main() -> int:
    if not EXPECTED_ID_PATH.exists():
        raise FileNotFoundError("Run scripts/build_extensions.py before detecting Chrome extension ID")
    expected_id = EXPECTED_ID_PATH.read_text(encoding="utf-8").strip()
    chrome = find_chrome()
    profile = Path(tempfile.mkdtemp(prefix="obi-chrome-id-"))
    port = "9227"
    proc = subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile}",
            f"--load-extension={EXTENSION_DIR.resolve()}",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        targets = []
        for _ in range(30):
            try:
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    targets = json.loads(response.read().decode("utf-8"))
                if targets:
                    break
            except Exception:
                time.sleep(1)

        extension_ids = []
        for target in targets:
            url = target.get("url") or ""
            if (
                target.get("type") == "service_worker"
                and url.startswith(f"chrome-extension://{expected_id}/")
            ):
                extension_id = url.split("/", 3)[2]
                extension_ids.append(extension_id)

        if not extension_ids:
            raise RuntimeError(
                "Chrome did not report this extension. This Chrome installation may ignore --load-extension; "
                "use the key-derived ID from chrome-extension-key-derived-id.txt when loading unpacked manually."
            )

        extension_id = extension_ids[0]
        OUTPUT_PATH.write_text(extension_id + "\n", encoding="utf-8")
        print(extension_id)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
