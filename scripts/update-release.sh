#!/usr/bin/env bash
set -euo pipefail

VAULT_PATH="${VAULT_PATH:-$HOME/Obsidian}"
SKIP_OPEN="${SKIP_OPEN:-0}"
SKIP_START_WORKER="${SKIP_START_WORKER:-0}"
DOWNLOAD_URL="https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest/download/bookmark-intelligence-source.zip"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/bookmark-intelligence-update.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

if command -v curl >/dev/null 2>&1; then
  curl --fail --location --silent --show-error "$DOWNLOAD_URL" --output "$TMP_ROOT/release.zip"
elif command -v wget >/dev/null 2>&1; then
  wget --https-only --quiet --output-document="$TMP_ROOT/release.zip" "$DOWNLOAD_URL"
else
  echo "curl or wget is required" >&2
  exit 1
fi

unzip -q "$TMP_ROOT/release.zip" -d "$TMP_ROOT/package"
ARGS=(--vault-path "$VAULT_PATH")
if [[ "$SKIP_OPEN" == "1" ]]; then ARGS+=(--skip-open); fi
if [[ "$SKIP_START_WORKER" == "1" ]]; then ARGS+=(--skip-start-worker); fi
"$TMP_ROOT/package/install.sh" "${ARGS[@]}"
echo "Release update finished. Existing config.toml was preserved when present."
