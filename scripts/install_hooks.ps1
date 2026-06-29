# Install project git hooks (pre-commit + commit-msg) — Windows native.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HooksDir = Join-Path $Root ".githooks"

if (-not (Test-Path $HooksDir)) {
    Write-Error "Hooks directory not found: $HooksDir"
}

git -C $Root config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Installed git hooks from .githooks (core.hooksPath=.githooks)"
