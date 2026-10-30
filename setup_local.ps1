param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv")) {
    & $Python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

New-Item -ItemType Directory -Force -Path "generated_reports" | Out-Null
New-Item -ItemType Directory -Force -Path "generated_sources" | Out-Null
New-Item -ItemType Directory -Force -Path ".sessions" | Out-Null

Write-Host ""
Write-Host "Local setup complete."
Write-Host "Python: $Root\.venv\Scripts\python.exe"
Write-Host ""
Write-Host "Next: install pbi-tools.core and add Claude Desktop config from LOCAL_SETUP.md"
