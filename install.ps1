param(
  [string]$VaultPath = "D:\obsidian",
  [switch]$ForceConfig,
  [switch]$RegenerateChromeKey,
  [switch]$RebuildNativeHost,
  [switch]$SkipOpen,
  [switch]$SkipStartWorker
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-ProjectPython {
  param([string[]]$Arguments)
  & ".\.venv\Scripts\python.exe" @Arguments
}

function Invoke-Agent {
  param([string[]]$Arguments)
  & ".\.venv\Scripts\bookmark-agent.exe" --config ".\config.toml" @Arguments
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Step "Preparing Python virtual environment"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 -m venv ".venv"
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv ".venv"
  } else {
    throw "Python 3.11+ was not found. Install Python first, then rerun install.ps1."
  }
}

Write-Step "Installing Python dependencies"
Invoke-ProjectPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-ProjectPython @("-m", "pip", "install", "-e", ".[build]")

Write-Step "Creating or reusing config.toml"
if ((Test-Path ".\config.toml") -and -not $ForceConfig) {
  Write-Host "Using existing config.toml. Pass -ForceConfig to recreate it."
} else {
  Invoke-Agent @("init-config", "--vault-path", $VaultPath, "--force")
}
Invoke-Agent @("init-db")

Write-Step "Building browser extension artifacts"
if ($RegenerateChromeKey) {
  Invoke-ProjectPython @(".\scripts\generate_chrome_manifest_key.py")
}
Invoke-ProjectPython @(".\scripts\build_extensions.py")

$ChromeExtensionIdPath = ".\outputs\chrome-extension-key-derived-id.txt"
if (-not (Test-Path $ChromeExtensionIdPath)) {
  throw "Chrome extension ID file was not generated: $ChromeExtensionIdPath"
}
$ChromeExtensionId = (Get-Content $ChromeExtensionIdPath -Raw).Trim()

if ((Test-Path ".\outputs\bookmark-agent-native.exe") -and -not $RebuildNativeHost) {
  Write-Step "Using bundled native host executable"
  Write-Host "Found .\outputs\bookmark-agent-native.exe. Pass -RebuildNativeHost to rebuild it from source."
} else {
  Write-Step "Building native host executable"
  Invoke-ProjectPython @(
    "-m",
    "PyInstaller",
    "--onefile",
    "--clean",
    "--name",
    "bookmark-agent-native",
    "--distpath",
    "outputs",
    "--workpath",
    "work\pyinstaller-build",
    "--specpath",
    "work\pyinstaller-spec",
    "scripts\native_host_launcher.py"
  )
}

$NativeHostPath = (Resolve-Path ".\outputs\bookmark-agent-native.exe").Path

Write-Step "Registering Chrome and Firefox native messaging hosts"
Invoke-Agent @(
  "install-native-host",
  "--browser",
  "chrome",
  "--host-path",
  $NativeHostPath,
  "--manifest-dir",
  ".\outputs",
  "--chrome-extension-id",
  $ChromeExtensionId
)
Invoke-Agent @(
  "install-native-host",
  "--browser",
  "firefox",
  "--host-path",
  $NativeHostPath,
  "--manifest-dir",
  ".\outputs"
)

Write-Step "Registering worker startup"
Invoke-Agent @("create-worker-shim", "--output", ".\outputs\bookmark-agent-worker.cmd")
Invoke-Agent @("install-worker-startup", "--command-path", ".\outputs\bookmark-agent-worker.cmd")

if (-not $SkipStartWorker) {
  Write-Step "Starting worker"
  $PythonPath = (Resolve-Path ".\.venv\Scripts\python.exe").Path
  $ConfigPath = (Resolve-Path ".\config.toml").Path
  Start-Process -FilePath $PythonPath -ArgumentList @("-m", "bookmark_agent.cli", "--config", $ConfigPath, "worker") -WorkingDirectory $ProjectRoot -WindowStyle Hidden
}

Write-Step "Running doctor"
Invoke-Agent @("doctor")

if (-not $SkipOpen) {
  Write-Step "Opening extension setup pages"
  Invoke-Agent @("open-extension-setup")
}

Write-Host ""
Write-Host "Installation finished." -ForegroundColor Green
Write-Host "Chrome extension folder: outputs\chrome-extension"
Write-Host "Chrome extension ID: $ChromeExtensionId"
Write-Host "Firefox manifest: outputs\firefox-extension\manifest.json"
Write-Host "Vault path: $VaultPath"
