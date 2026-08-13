param(
  [string]$VaultPath = "D:\obsidian",
  [switch]$SkipOpen
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (-not (Test-Path ".git")) {
  throw "This updater expects a Git checkout: $ProjectRoot"
}

Write-Host "Fetching latest Bookmark Intelligence code..." -ForegroundColor Cyan
git pull --ff-only

$arguments = @("-VaultPath", $VaultPath)
if ($SkipOpen) { $arguments += "-SkipOpen" }
& powershell -ExecutionPolicy Bypass -File ".\install.ps1" @arguments

Write-Host "Update finished. Existing config.toml was preserved." -ForegroundColor Green
