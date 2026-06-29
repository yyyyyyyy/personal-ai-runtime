# Personal AI Runtime — Windows PowerShell task runner (Makefile.ps1 equivalent)
param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Desktop = Join-Path $Root "desktop"

function Invoke-Backend {
    param([string[]]$Args)
    Push-Location $Backend
    try {
        & python @Args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

function Invoke-Frontend {
    param([string[]]$Args)
    Push-Location $Frontend
    try {
        & npm @Args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

switch ($Task) {
    "help" {
        Write-Host @"
Available tasks:
  install          Install backend, frontend, desktop dependencies
  install-hooks    Install git hooks (or run: .\install-hooks.cmd)
  dev              Start backend + frontend (manual; run in separate terminals)
  test-backend     Run backend pytest
  test-frontend    Run frontend unit tests
  lint             Run ruff on backend
  typecheck        Run mypy on backend
  boundary         Kernel boundary guard
  docker-up        docker compose up --build
  docker-down      docker compose down
"@
    }
    "install" {
        Push-Location $Backend; pip install -r requirements.txt; Pop-Location
        Push-Location $Frontend; npm ci; Pop-Location
        Push-Location $Desktop; npm ci; Pop-Location
    }
    "install-hooks" {
        $hookScript = Join-Path $Root "scripts\install_hooks.ps1"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $hookScript
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "test-backend" {
        Invoke-Backend @("-m", "pytest", "tests/", "-q", "-m", "not live_llm")
    }
    "test-frontend" {
        Push-Location $Frontend
        npx tsc --noEmit
        npm test
        Pop-Location
    }
    "lint" {
        Push-Location $Backend
        ruff check app/
        Pop-Location
    }
    "typecheck" {
        $agents = @(
            "app/core/agents/brain.py", "app/core/agents/conversation.py",
            "app/core/agents/planner.py", "app/core/agents/critic.py",
            "app/core/agents/llm_router.py", "app/core/agents/memory_engine.py",
            "app/core/agents/memory_extractor.py"
        )
        Push-Location $Backend
        mypy app/core/runtime/ app/core/harness/ @agents app/product/ app/api/ app/main.py scripts/ --ignore-missing-imports
        Pop-Location
    }
    "boundary" {
        Invoke-Backend @("scripts/check_boundary.py")
    }
    "docker-up" {
        docker compose up --build
    }
    "docker-down" {
        docker compose down
    }
    default {
        Write-Error "Unknown task: $Task. Run: .\Makefile.ps1 help"
    }
}
