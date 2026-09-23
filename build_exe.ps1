# Build standalone Windows executable (requires: pip install pyinstaller)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller

& .\.venv\Scripts\pyinstaller.exe `
    --noconfirm `
    --windowed `
    --name "AGHomeSync" `
    --collect-all requests `
    run_app.py

Write-Host ""
Write-Host "Built: $PSScriptRoot\dist\AGHomeSync.exe"
Write-Host "Copy dist\AGHomeSync.exe anywhere; settings live in %LOCALAPPDATA%\AGHomeSync"
