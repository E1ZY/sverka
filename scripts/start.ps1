$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Сначала создайте .venv и установите зависимости по README.md'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    throw 'Сначала соберите интерфейс: cd frontend; npm ci; npm run build'
}
Write-Host 'Откройте http://127.0.0.1:8000. Для остановки нажмите Ctrl+C.'
& $pythonExecutable -m uvicorn app.main:app --host 127.0.0.1 --port 8000
