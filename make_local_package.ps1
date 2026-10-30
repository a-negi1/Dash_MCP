param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageName = "dash_mcp-pbi-local"
$BuildRoot = Join-Path $env:TEMP "$PackageName-package"
$Stage = Join-Path $BuildRoot $PackageName

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path (Split-Path -Parent $Root) "$PackageName.zip"
}

if (Test-Path $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$ExcludeDirs = @(
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".sessions",
    "generated_reports",
    "generated_sources"
)

$ExcludeFiles = @(
    "*.pyc",
    ".env"
)

Get-ChildItem -LiteralPath $Root -Force | ForEach-Object {
    if ($_.PSIsContainer -and ($ExcludeDirs -contains $_.Name)) {
        return
    }
    foreach ($pattern in $ExcludeFiles) {
        if ($_.Name -like $pattern) {
            return
        }
    }
    Copy-Item -LiteralPath $_.FullName -Destination $Stage -Recurse -Force
}

if (Test-Path $Output) {
    Remove-Item -LiteralPath $Output -Force
}

Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Output -Force
Remove-Item -LiteralPath $BuildRoot -Recurse -Force

Write-Host "Package created:"
Write-Host $Output
