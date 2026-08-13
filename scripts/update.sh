#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -d .git ]]; then
  echo "This updater expects a Git checkout: $PROJECT_ROOT" >&2
  exit 1
fi

git pull --ff-only
ARGS=(--vault-path "${VAULT_PATH:-$HOME/Obsidian}")
if [[ "${SKIP_OPEN:-0}" == "1" ]]; then
  ARGS+=(--skip-open)
fi
./install.sh "${ARGS[@]}"
echo "Update finished. Existing config.toml was preserved."
