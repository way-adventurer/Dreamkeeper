$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

$Python = "$Root\.venv\Scripts\python.exe"
& $Python -c "import runrelay,PyInstaller"
if ($LASTEXITCODE -ne 0) {
    & $Python -c "import importlib.util,sys; sys.exit(importlib.util.find_spec('pip') is None)"
    if ($LASTEXITCODE -eq 0) {
        & $Python -m pip install -e . pyinstaller
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $Python -e . pyinstaller
    } else {
        throw "Install pip or uv to build the Windows executable."
    }
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}
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
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "Built: $Root\dist\Dreamkeeper.exe"
$runningCopy = Get-Process -Name Dreamkeeper -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq "$Root\Dreamkeeper.exe" }
if ($runningCopy) {
    throw "Close the running root Dreamkeeper.exe before replacing it."
}
Copy-Item -LiteralPath "$Root\dist\Dreamkeeper.exe" -Destination "$Root\Dreamkeeper.exe" -Force
foreach ($alias in @("$Root\dist\Dreamkeeper-fixed.exe", "$Root\Dreamkeeper-fixed.exe")) {
    if (Test-Path -LiteralPath $alias) { Remove-Item -LiteralPath $alias -Force }
}
$rootHash = (Get-FileHash -LiteralPath "$Root\Dreamkeeper.exe" -Algorithm SHA256).Hash
$distHash = (Get-FileHash -LiteralPath "$Root\dist\Dreamkeeper.exe" -Algorithm SHA256).Hash
if ($rootHash -ne $distHash) { throw "Root and dist executables differ." }
if (@(Get-ChildItem -LiteralPath $Root -File -Filter '*.exe').Count -ne 1 -or
    @(Get-ChildItem -LiteralPath "$Root\dist" -File -Filter '*.exe').Count -ne 1) {
    throw "Expected only Dreamkeeper.exe in the project root and dist."
}
Write-Host "One-click copy: $Root\Dreamkeeper.exe"
