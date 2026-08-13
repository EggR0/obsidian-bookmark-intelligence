param(
  [string]$VaultPath = "D:\obsidian",
  [switch]$SkipOpen,
  [switch]$SkipStartWorker
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$downloadUrl = "https://github.com/EggR0/obsidian-bookmark-intelligence/releases/latest/download/bookmark-intelligence-windows.zip"
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("bookmark-intelligence-update-" + [guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $temporaryRoot "bookmark-intelligence-windows.zip"
$extractPath = Join-Path $temporaryRoot "package"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

try {
  New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
  Write-Host "Downloading latest Bookmark Intelligence release..." -ForegroundColor Cyan
  Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
  Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath -Force
  # Stage the release into the persistent install directory before running it.
  # Native Messaging manifests must not point into the temporary download folder.
  Copy-Item -Path (Join-Path $extractPath "*") -Destination $projectRoot -Recurse -Force
  $installer = Join-Path $projectRoot "install.ps1"
  if (-not (Test-Path $installer)) { throw "The downloaded release did not contain install.ps1." }
  $arguments = @("-VaultPath", $VaultPath)
  if ($SkipOpen) { $arguments += "-SkipOpen" }
  if ($SkipStartWorker) { $arguments += "-SkipStartWorker" }
  & powershell -ExecutionPolicy Bypass -File $installer @arguments
  Write-Host "Release update finished. Existing config.toml was preserved when present." -ForegroundColor Green
} finally {
  if (Test-Path $temporaryRoot) { Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
