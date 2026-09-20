$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -e .
& ".venv\Scripts\python.exe" -m pip install pyinstaller
& ".venv\Scripts\pyinstaller.exe" `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name Dreamkeeper `
    --collect-submodules lark_oapi.ws `
    --collect-submodules lark_oapi.core `
    --paths src `
    packaging\windows_launcher.py

Write-Host "Built: $Root\dist\Dreamkeeper.exe"
Copy-Item -LiteralPath "$Root\dist\Dreamkeeper.exe" -Destination "$Root\Dreamkeeper.exe" -Force
Write-Host "One-click copy: $Root\Dreamkeeper.exe"
