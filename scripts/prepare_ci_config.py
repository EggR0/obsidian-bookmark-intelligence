from __future__ import annotations

import argparse
import os
from pathlib import Path
import re


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an isolated CI config from config.example.toml")
    parser.add_argument("--output", type=Path, default=Path("config.toml"))
    parser.add_argument("--vault-path", type=Path)
    args = parser.parse_args()

    vault_path = args.vault_path or Path(os.environ.get("RUNNER_TEMP", ".")) / "bookmark-intelligence-ci-vault"
    vault_path = vault_path.resolve()
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / ".obsidian").mkdir(exist_ok=True)

    template = Path("config.example.toml").read_text(encoding="utf-8")
    toml_literal_path = str(vault_path).replace("'", "''")
    config = re.sub(
        r"^vault_path = .*$",
        lambda _match: f"vault_path = '{toml_literal_path}'",
        template,
        flags=re.MULTILINE,
    )
    args.output.write_text(config, encoding="utf-8")
    print(f"Created CI config: {args.output.resolve()}")
    print(f"CI vault: {vault_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
