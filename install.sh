#!/usr/bin/env bash
set -euo pipefail

VAULT_PATH="${VAULT_PATH:-$HOME/Obsidian}"
FORCE_CONFIG=0
SKIP_OPEN=0
SKIP_START_WORKER=0
PYTHON_BIN="${PYTHON_BIN:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault-path)
      VAULT_PATH="$2"
      shift 2
      ;;
    --force-config)
      FORCE_CONFIG=1
      shift
      ;;
    --skip-open)
      SKIP_OPEN=1
      shift
      ;;
    --skip-start-worker)
      SKIP_START_WORKER=1
      shift
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --vault-path PATH     Obsidian vault path. Default: $HOME/Obsidian
  --force-config        Recreate config.toml even if it already exists.
  --skip-open           Do not open browser extension setup pages.
  --skip-start-worker   Do not start/register the worker after install.
  --python PATH         Python 3.11+ executable. Default: python3
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

step() {
  printf '\n==> %s\n' "$1"
}

agent() {
  "$PROJECT_ROOT/.venv/bin/bookmark-agent" --config "$PROJECT_ROOT/config.toml" "$@"
}

step "Preparing Python virtual environment"
if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv"
fi

step "Installing Python dependencies"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install -e '.[build]'

step "Creating or reusing config.toml"
if [[ -f "$PROJECT_ROOT/config.toml" && "$FORCE_CONFIG" -eq 0 ]]; then
  echo "Using existing config.toml. Pass --force-config to recreate it."
else
  agent init-config --vault-path "$VAULT_PATH" --force
fi
agent init-db

step "Building browser extension artifacts"
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/build_extensions.py"

CHROME_EXTENSION_ID_FILE="$PROJECT_ROOT/outputs/chrome-extension-key-derived-id.txt"
if [[ ! -f "$CHROME_EXTENSION_ID_FILE" ]]; then
  echo "Chrome extension ID file was not generated: $CHROME_EXTENSION_ID_FILE" >&2
  exit 1
fi
CHROME_EXTENSION_ID="$(tr -d '\r\n' < "$CHROME_EXTENSION_ID_FILE")"

step "Creating native host launcher"
mkdir -p "$PROJECT_ROOT/outputs"
NATIVE_HOST="$PROJECT_ROOT/outputs/bookmark-agent-native"
cat > "$NATIVE_HOST" <<EOF
#!/usr/bin/env sh
cd "$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" -m bookmark_agent.cli --config "$PROJECT_ROOT/config.toml" native-host
EOF
chmod +x "$NATIVE_HOST"

step "Installing Chrome and Firefox native messaging manifests"
agent install-native-host \
  --browser chrome \
  --host-path "$NATIVE_HOST" \
  --manifest-dir "$PROJECT_ROOT/outputs" \
  --chrome-extension-id "$CHROME_EXTENSION_ID"
agent install-native-host \
  --browser firefox \
  --host-path "$NATIVE_HOST" \
  --manifest-dir "$PROJECT_ROOT/outputs"

register_worker_linux() {
  if command -v systemctl >/dev/null 2>&1; then
    mkdir -p "$HOME/.config/systemd/user"
    SERVICE_PATH="$HOME/.config/systemd/user/obsidian-bookmark-intelligence-worker.service"
    cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Obsidian Bookmark Intelligence worker

[Service]
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/.venv/bin/python -m bookmark_agent.cli --config $PROJECT_ROOT/config.toml worker
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload || true
    systemctl --user enable --now obsidian-bookmark-intelligence-worker.service || true
    echo "Registered user systemd service: $SERVICE_PATH"
    return
  fi

  mkdir -p "$HOME/.config/autostart"
  DESKTOP_PATH="$HOME/.config/autostart/obsidian-bookmark-intelligence-worker.desktop"
  cat > "$DESKTOP_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=Obsidian Bookmark Intelligence Worker
Exec=$PROJECT_ROOT/.venv/bin/python -m bookmark_agent.cli --config $PROJECT_ROOT/config.toml worker
X-GNOME-Autostart-enabled=true
EOF
  echo "Registered XDG autostart file: $DESKTOP_PATH"
}

register_worker_macos() {
  mkdir -p "$HOME/Library/LaunchAgents"
  PLIST_PATH="$HOME/Library/LaunchAgents/com.local.obsidian-bookmark-intelligence.worker.plist"
  cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.obsidian-bookmark-intelligence.worker</string>
  <key>WorkingDirectory</key>
  <string>$PROJECT_ROOT</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PROJECT_ROOT/.venv/bin/python</string>
    <string>-m</string>
    <string>bookmark_agent.cli</string>
    <string>--config</string>
    <string>$PROJECT_ROOT/config.toml</string>
    <string>worker</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
</dict>
</plist>
EOF
  launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
  launchctl load "$PLIST_PATH" >/dev/null 2>&1 || true
  echo "Registered LaunchAgent: $PLIST_PATH"
}

if [[ "$SKIP_START_WORKER" -eq 0 ]]; then
  step "Registering worker startup"
  case "$(uname -s)" in
    Darwin)
      register_worker_macos
      ;;
    Linux)
      register_worker_linux
      ;;
    *)
      echo "Worker startup registration is not implemented for this OS."
      ;;
  esac
fi

step "Running doctor"
agent doctor

if [[ "$SKIP_OPEN" -eq 0 ]]; then
  step "Opening extension setup pages"
  case "$(uname -s)" in
    Darwin)
      open "chrome://extensions" >/dev/null 2>&1 || true
      open "about:debugging#/runtime/this-firefox" >/dev/null 2>&1 || true
      ;;
    Linux)
      xdg-open "chrome://extensions" >/dev/null 2>&1 || true
      xdg-open "about:debugging#/runtime/this-firefox" >/dev/null 2>&1 || true
      ;;
  esac
fi

printf '\nInstallation finished.\n'
printf 'Chrome extension folder: outputs/chrome-extension\n'
printf 'Chrome extension ID: %s\n' "$CHROME_EXTENSION_ID"
printf 'Firefox manifest: outputs/firefox-extension/manifest.json\n'
printf 'Vault path: %s\n' "$VAULT_PATH"
