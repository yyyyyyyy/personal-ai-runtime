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

function Invoke-BackendModule {
    param([string]$Module, [string[]]$ExtraArgs = @())
    Invoke-Backend (@("-m", $Module) + $ExtraArgs)
}

function Invoke-ModuleList {
    param([string[]]$Modules)
    foreach ($mod in $Modules) {
        Write-Host ">> python -m $mod"
        Invoke-BackendModule $mod
    }
}

$StaticModules = @(
    "scripts.check_dependency_sync",
    "scripts.check_version_sync",
    "scripts.check_capability_policy_consistency",
    "scripts.check_doc_links",
    "scripts.check_doc_table_sync",
    "scripts.check_doc_line_refs",
    "scripts.check_boundary",
    "scripts.check_execution_ownership",
    "scripts.check_concept_growth"
)

$RuntimeModules = @(
    "scripts.verify_alembic",
    "scripts.verify_api_mcp_smoke",
    "scripts.check_projection_provenance",
    "scripts.verify_rebuild",
    "scripts.verify_snapshot_rebuild",
    "scripts.verify_conversation_rebuild",
    "scripts.verify_goal_rebuild",
    "scripts.verify_work_items_goal_rebuild",
    "scripts.verify_export_roundtrip",
    "scripts.verify_memory_lifecycle",
    "scripts.verify_inbox_audit",
    "scripts.verify_egress",
    "scripts.verify_connector",
    "scripts.verify_vector_consistency",
    "scripts.verify_memory_index_repairs",
    "scripts.verify_tool_calls_audit"
)

switch ($Task) {
    "help" {
        Write-Host @"
Available tasks:
  install              Install backend, frontend, desktop dependencies (hash lock)
  dependency-sync      Verify requirements / pyproject / lock stamps
  install-hooks        Install git hooks (or run: .\install-hooks.cmd)
  test-backend         Run backend pytest
  test-frontend        Run frontend unit tests
  lint                 Run ruff on backend
  typecheck            Run mypy on backend
  boundary             Kernel boundary guard
  backend-ci-static    Static guards (aligned with Makefile)
  backend-ci-runtime   Runtime verifies + pytest (aligned with Makefile)
  backend-ci-core      Static then runtime
  docker-up            docker compose up --build
  docker-down          docker compose down

Note: Unix ``make backend-ci-core`` runs static/runtime waves with -j parallel.
PowerShell runs modules sequentially for reliable exit codes; use make/WSL for parallel CI.
"@
    }
    "install" {
        Push-Location $Backend
        python -m scripts.check_dependency_sync
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        python -m pip install --require-hashes -r requirements.lock
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        Pop-Location
        Push-Location $Frontend; npm ci; Pop-Location
        Push-Location $Desktop; npm ci; Pop-Location
    }
    "dependency-sync" {
        Invoke-BackendModule "scripts.check_dependency_sync"
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
        Push-Location $Backend
        python -m mypy app/ scripts/ --ignore-missing-imports
        Pop-Location
    }
    "boundary" {
        Invoke-BackendModule "scripts.check_boundary"
    }
    "backend-ci-static" {
        Write-Host "Running static checks..."
        Push-Location $Backend
        python -m compileall app/ -q
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        ruff check app/
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        python -m mypy app/ scripts/ --ignore-missing-imports
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        Pop-Location
        Invoke-ModuleList $StaticModules
        Write-Host "backend-ci-static checks passed"
    }
    "backend-ci-runtime" {
        Write-Host "Running runtime verifies..."
        Push-Location $Backend
        python -m pytest tests/ -q -m "not live_llm"
        if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
        Pop-Location
        Invoke-ModuleList $RuntimeModules
        Write-Host "backend-ci-runtime checks passed"
    }
    "backend-ci-core" {
        & $PSCommandPath "backend-ci-static"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $PSCommandPath "backend-ci-runtime"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "backend-ci-core checks passed"
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
