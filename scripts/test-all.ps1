[CmdletBinding()]
param(
    [switch]$Frontend,
    [string]$DataWorkspace
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Command $($Arguments -join ' ')"
    }
}

function Test-PythonRepository {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath (Join-Path $Path "pyproject.toml") -PathType Leaf)) {
        throw "Missing sibling repository for $Name`: $Path"
    }

    Write-Host "`n== $Name =="
    Push-Location $Path
    try {
        Invoke-CheckedCommand uv sync --frozen
        Invoke-CheckedCommand uv run ruff check src tests
        Invoke-CheckedCommand uv run python -m pytest
        Invoke-CheckedCommand uv build
    }
    finally {
        Pop-Location
    }
}

$dashboardRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$portfolioRoot = Split-Path $dashboardRoot -Parent
$repositories = @(
    @{ Name = "portfolio-core"; Path = (Join-Path $portfolioRoot "portfolio-core") },
    @{ Name = "portfolio-market-data"; Path = (Join-Path $portfolioRoot "portfolio-market-data") },
    @{ Name = "portfolio-crypto-data"; Path = (Join-Path $portfolioRoot "portfolio-crypto-data") },
    @{ Name = "portfolio-dashboard"; Path = $dashboardRoot }
)

foreach ($repository in $repositories) {
    Test-PythonRepository -Name $repository.Name -Path $repository.Path
}

if ($Frontend) {
    Write-Host "`n== portfolio-dashboard frontend =="
    Push-Location (Join-Path $dashboardRoot "src\portfolio_dashboard\frontend")
    try {
        Invoke-CheckedCommand npm.cmd ci
        Invoke-CheckedCommand npm.cmd audit --audit-level=low
        Invoke-CheckedCommand npm.cmd run build
    }
    finally {
        Pop-Location
    }
}

if ($DataWorkspace) {
    $resolvedDataWorkspace = (Resolve-Path $DataWorkspace).Path
    Write-Host "`n== tag-backed portfolio-data environment =="
    Push-Location $resolvedDataWorkspace
    try {
        Invoke-CheckedCommand uv sync --frozen
        Invoke-CheckedCommand uv run python scripts/validate_workspace.py
        Invoke-CheckedCommand uv run portfolio-market --help
        Invoke-CheckedCommand uv run portfolio-crypto --help
    }
    finally {
        Pop-Location
    }
}

Write-Host "`nAll requested checks passed."
