from __future__ import annotations

import os
from pathlib import Path
import sys

from .config import load_config
from .database import init_db
from .native_host import run_native_host


def find_config() -> Path:
    env_path = os.environ.get("BOOKMARK_AGENT_CONFIG")
    if env_path:
        return Path(env_path).resolve()

    candidates = [
        Path.cwd() / "config.toml",
        Path(sys.executable).resolve().parent / "config.toml",
        Path(sys.executable).resolve().parent.parent / "config.toml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not find config.toml. Place it beside bookmark-agent-native.exe, "
        "in the project root, or set BOOKMARK_AGENT_CONFIG."
    )


def main() -> int:
    config = load_config(find_config())
    init_db(config.database.path)
    run_native_host(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
