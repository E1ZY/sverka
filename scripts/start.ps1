$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Сначала создайте .venv и установите зависимости по README.md'
}

# An existing venv launcher can still point to a removed base interpreter.
# Probe the executable itself before rebuilding the UI or announcing the server.
$pythonProbe = [System.Diagnostics.Process]::new()
try {
    $pythonProbe.StartInfo.FileName = $pythonExecutable
    $pythonProbe.StartInfo.Arguments = '-c "import json,struct,sys; print(json.dumps(dict(version=list(sys.version_info[:3]),bits=struct.calcsize(chr(80))*8,executable=sys.executable,prefix=sys.prefix,base_prefix=sys.base_prefix)))"'
    $pythonProbe.StartInfo.WorkingDirectory = $projectRoot
    $pythonProbe.StartInfo.UseShellExecute = $false
    $pythonProbe.StartInfo.CreateNoWindow = $true
    $pythonProbe.StartInfo.RedirectStandardOutput = $true
    $pythonProbe.StartInfo.RedirectStandardError = $true
    $pythonProbe.StartInfo.EnvironmentVariables['PYTHONUTF8'] = '1'
    $pythonProbe.StartInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $pythonProbe.StartInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    [void]$pythonProbe.Start()
    $pythonOutput = $pythonProbe.StandardOutput.ReadToEndAsync()
    $pythonError = $pythonProbe.StandardError.ReadToEndAsync()
    if (-not $pythonProbe.WaitForExit(15000)) {
        $pythonProbe.Kill()
        throw 'Python не ответил за 15 секунд.'
    }
    if ($pythonProbe.ExitCode -ne 0) {
        throw $pythonError.GetAwaiter().GetResult().Trim()
    }
    $pythonInfo = $pythonOutput.GetAwaiter().GetResult() | ConvertFrom-Json
    $expectedVenv = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.venv'))
    if ([System.IO.Path]::GetFullPath($pythonInfo.prefix) -ne $expectedVenv -or $pythonInfo.prefix -eq $pythonInfo.base_prefix) {
        throw 'Интерпретатор запущен вне окружения .venv этого проекта.'
    }
    if ($pythonInfo.version[0] -ne 3 -or $pythonInfo.version[1] -ne 12 -or $pythonInfo.bits -ne 64) {
        throw 'Для проекта требуется Python 3.12 x64. Пересоздайте .venv по разделу 1.4 README.md.'
    }
} catch {
    throw "Не удалось запустить Python из .venv. Причина: $($_.Exception.Message)`nПроверьте базовый Python в .venv\pyvenv.cfg. Если он удалён, восстановите окружение установленным Python 3.12 x64: py -3.12 -m venv --upgrade .venv. Подробности: README.md, раздел 1.8."
} finally {
    $pythonProbe.Dispose()
}
Write-Host ('Python проекта: {0} (Python {1}, x64)' -f $pythonInfo.executable, ($pythonInfo.version -join '.'))

# Choose access on first installation; keep the existing selection on later runs.
try {
    # PowerShell 5.1 must forward the whole argparse error, including the remedy.
    $ErrorActionPreference = 'Continue'
    & $pythonExecutable (Join-Path $PSScriptRoot 'configure_auth.py') --ensure --http
} finally {
    $ErrorActionPreference = 'Stop'
}
if ($LASTEXITCODE -ne 0) {
    throw 'Не удалось настроить режим доступа. Следуйте подсказке выше и повторите запуск.'
}

$frontendRoot = Join-Path $projectRoot 'frontend'
$outputRoot = Join-Path $frontendRoot 'dist'
$indexPath = Join-Path $outputRoot 'index.html'
$buildStatePath = Join-Path $outputRoot '.sverka-build.json'

function Get-FilesFingerprint {
    param([string]$Root, [System.IO.FileInfo[]]$Files)
    # Include relative names so additions, deletions and renames invalidate the build.
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $entries = @($Files | Sort-Object FullName | ForEach-Object {
            $relativePath = $_.FullName.Substring($Root.Length + 1).Replace('\', '/')
            $stream = [System.IO.File]::OpenRead($_.FullName)
            try {
                $fileHash = [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '')
            } finally {
                $stream.Dispose()
            }
            $relativePath + ':' + $fileHash
        })
        $bytes = [System.Text.Encoding]::UTF8.GetBytes(($entries -join "`n"))
        return [System.BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-', '')
    } finally {
        $hasher.Dispose()
    }
}

function Get-SourceFingerprint {
    # Vite inputs: root configuration (including .env files), source and public assets.
    # TypeScript writes *.tsbuildinfo itself; it must not trigger the next build.
    $files = @(Get-ChildItem -LiteralPath $frontendRoot -File -Force |
        Where-Object { $_.Name -notlike '*.tsbuildinfo' })
    foreach ($folder in @('src', 'public')) {
        $path = Join-Path $frontendRoot $folder
        if (Test-Path -LiteralPath $path -PathType Container) {
            $files += @(Get-ChildItem -LiteralPath $path -File -Recurse -Force)
        }
    }
    return Get-FilesFingerprint $frontendRoot $files
}

function Get-OutputFingerprint {
    $files = @(Get-ChildItem -LiteralPath $outputRoot -File -Recurse -Force |
        Where-Object { $_.FullName -ne $buildStatePath })
    return Get-FilesFingerprint $outputRoot $files
}

$sourceFingerprint = Get-SourceFingerprint
$buildState = $null
if (Test-Path -LiteralPath $buildStatePath -PathType Leaf) {
    try {
        $buildState = Get-Content -LiteralPath $buildStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        # A missing or interrupted state write requires a fresh build.
    }
}
$upToDate = (Test-Path -LiteralPath $indexPath -PathType Leaf) -and
    $buildState -and $buildState.version -eq 1 -and
    $buildState.sources -eq $sourceFingerprint -and
    $buildState.output -eq (Get-OutputFingerprint)

if (-not $upToDate) {
    $npmCommand = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $npmCommand) {
        throw 'Для пересборки нужен Node.js с npm. Установите Node.js LTS по разделу 1.3 README.md и откройте новое окно PowerShell.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules') -PathType Container)) {
        throw 'Не установлены зависимости интерфейса. В папке frontend выполните npm.cmd ci, затем повторите запуск.'
    }
    # Invalidate before npm runs: a failed/partial build must never be treated as current.
    if (Test-Path -LiteralPath $buildStatePath -PathType Leaf) {
        Remove-Item -LiteralPath $buildStatePath -Force
    }
    Write-Host 'Интерфейс изменился или сборка отсутствует. Пересобираем...'
    Push-Location -LiteralPath $frontendRoot
    try {
        & $npmCommand.Source run build
        if ($LASTEXITCODE -ne 0) {
            throw 'Сборка интерфейса завершилась ошибкой. Исправьте ошибки выше и повторите запуск. При изменении package.json или package-lock.json сначала выполните npm.cmd ci в frontend.'
        }
    } finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
        throw 'Сборка не создала frontend/dist/index.html. Сервер не запущен.'
    }
    if ((Get-SourceFingerprint) -ne $sourceFingerprint) {
        throw 'Исходники изменились во время сборки. Повторите запуск, чтобы собрать актуальную версию.'
    }
    $buildState = @{ version = 1; sources = $sourceFingerprint; output = Get-OutputFingerprint }
    [System.IO.File]::WriteAllText($buildStatePath, ($buildState | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
} else {
    Write-Host 'Интерфейс актуален. Пересборка не требуется.'
}
Write-Host 'Откройте http://127.0.0.1:8000. Для остановки нажмите Ctrl+C.'
& $pythonExecutable -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
