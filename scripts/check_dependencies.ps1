[CmdletBinding()]
param(
    [switch]$Project,
    [switch]$Json,
    [string]$PythonExe,
    [ValidateRange(1, 120)][int]$TimeoutSeconds = 15
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
$checks = [System.Collections.Generic.List[object]]::new()
$pythonInstall = 'Установите Python 3.12 x64: winget install --exact --id Python.Python.3.12. Затем откройте новое окно PowerShell. README: раздел 1.3.'
$nodeInstall = 'Установите Node.js LTS вместе с npm: winget install --exact --id OpenJS.NodeJS.LTS. Затем откройте новое окно PowerShell. README: раздел 1.3.'

function Add-Check {
    param([string]$Name, [string]$Status, [string]$Detail, [string]$Hint = '')
    $checks.Add([pscustomobject]@{ name = $Name; status = $Status; detail = $Detail; hint = $Hint })
}

function ConvertTo-ProcessArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows argv quoting; do not interpret arguments as PowerShell code.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-Probe {
    param([string]$Executable, [string[]]$Arguments)
    $process = [System.Diagnostics.Process]::new()
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $quoted = @($Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ })
    $info.Arguments = $quoted -join ' '
    if ([System.IO.Path]::GetExtension($Executable) -in @('.cmd', '.bat')) {
        $info.FileName = $env:ComSpec
        $info.Arguments = '/d /s /c ""' + $Executable + '" ' + ($quoted -join ' ') + '"'
    }
    $info.WorkingDirectory = $projectRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $info.EnvironmentVariables['PYTHONUTF8'] = '1'
    $info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $info.EnvironmentVariables['PYTHON_MANAGER_AUTOMATIC_INSTALL'] = 'false'
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            return [pscustomobject]@{ exitCode = -1; output = ''; error = "Проверка превысила $TimeoutSeconds с." }
        }
        return [pscustomobject]@{
            exitCode = $process.ExitCode
            output = $outputTask.GetAwaiter().GetResult().Trim()
            error = $errorTask.GetAwaiter().GetResult().Trim()
        }
    } catch {
        return [pscustomobject]@{ exitCode = -1; output = ''; error = $_.Exception.Message }
    } finally {
        $process.Dispose()
    }
}

function Find-Tool {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }
    return $null
}

$pyPath = Find-Tool @('py.exe', 'py')
$managerPath = Find-Tool @('pymanager.exe', 'pymanager')
$pyHint = 'Для команды py включите Python Launcher в установщике Python 3.12 x64 или установите Python Install Manager, затем откройте новое окно PowerShell. Если Python 3.12 x64 уже найден, вместо py -3.12 используйте его полный путь (в PowerShell: & "C:\путь\к\python.exe"). README: раздел 1.3.'
if (-not $pyPath) {
    Add-Check 'py (необязателен)' 'WARN' 'Команда py не найдена в PATH; команды py -3.12 из README недоступны.' $pyHint
} elseif ($pyPath -match '\\Microsoft\\WindowsApps\\' -and -not $managerPath) {
    Add-Check 'py (необязателен)' 'WARN' "Найден Windows Store alias: $pyPath; установленный Python Install Manager не найден." $pyHint
} else {
    $py = Invoke-Probe $pyPath @('-3.12', '--version')
    if ($py.exitCode -eq 0 -and $py.output -match '^Python 3\.12\.\d+\s*$') {
        Add-Check 'py (необязателен)' 'OK' "$($py.output); $pyPath; команда py -3.12 работает."
    } else {
        $pyDetail = ($py.output + ' ' + $py.error).Trim()
        Add-Check 'py (необязателен)' 'WARN' "Найден $pyPath, но py -3.12 --version не подтвердил Python 3.12: $pyDetail" ($pythonInstall + ' ' + $pyHint)
    }
}

$candidates = [System.Collections.Generic.List[object]]::new()
if ($PythonExe) {
    $candidates.Add([pscustomobject]@{ path = $PythonExe; prefix = @() })
} else {
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $candidates.Add([pscustomobject]@{ path = $venvPython; prefix = @() })
    }
    foreach ($hive in @('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE')) {
        try {
            $installDir = [Microsoft.Win32.Registry]::GetValue("$hive\SOFTWARE\Python\PythonCore\3.12\InstallPath", '', $null)
            if ($installDir) {
                $candidatePath = Join-Path $installDir 'python.exe'
                if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
                    $candidates.Add([pscustomobject]@{ path = $candidatePath; prefix = @() })
                }
            }
        } catch { }
    }
    if ($managerPath) {
        # Unlike the generic Store alias, this is the installed Python manager.
        # Automatic installation is disabled in Invoke-Probe's child environment.
        $candidates.Add([pscustomobject]@{ path = $managerPath; prefix = @('exec', '-V:3.12') })
    }
    foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
        $commands = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
        foreach ($command in $commands) {
            # Store aliases can open an installer. Prefer real executables and registry entries.
            if ($command.Source -match '\\Microsoft\\WindowsApps\\') { continue }
            $prefix = @()
            if ($name -eq 'py.exe') { $prefix = @('-3.12') }
            $candidates.Add([pscustomobject]@{ path = $command.Source; prefix = $prefix })
        }
    }
}

$pythonInfo = $null
$fallbackPython = $null
$pythonFailure = 'Рабочий Python не найден. Windows Store alias не считается установленным интерпретатором.'
$pythonCode = "import json,struct,sys; print(json.dumps(dict(version=list(sys.version_info[:3]),bits=struct.calcsize('P')*8,executable=sys.executable)))"
foreach ($candidate in $candidates) {
    $probe = Invoke-Probe $candidate.path (@($candidate.prefix) + @('-c', $pythonCode))
    if ($probe.exitCode -eq 0) {
        try {
            $info = $probe.output | ConvertFrom-Json
            if ($info.version.Count -eq 3 -and $info.executable) {
                $chosenExplicitly = $PythonExe -or $candidate.path -eq (Join-Path $projectRoot '.venv\Scripts\python.exe')
                if ($chosenExplicitly -or ($info.version[0] -eq 3 -and $info.version[1] -eq 12 -and $info.bits -eq 64)) {
                    $pythonInfo = $info
                    break
                }
                if (-not $fallbackPython) { $fallbackPython = $info }
            }
        } catch { }
    }
    $pythonFailure = "Не удалось запустить $($candidate.path): $($probe.error)"
}
if (-not $pythonInfo -and $fallbackPython) { $pythonInfo = $fallbackPython }

if ($pythonInfo) {
    $pythonVersion = $pythonInfo.version -join '.'
    $pythonStatus = 'OK'
    if ($pythonInfo.version[0] -ne 3 -or $pythonInfo.version[1] -ne 12 -or $pythonInfo.bits -ne 64) { $pythonStatus = 'ERROR' }
    Add-Check 'Python 3.12 x64' $pythonStatus "$pythonVersion, $($pythonInfo.bits)-bit; $($pythonInfo.executable)" $(if ($pythonStatus -eq 'ERROR') { $pythonInstall } else { '' })
    $pip = Invoke-Probe $pythonInfo.executable @('-m', 'pip', '--version')
    if ($pip.exitCode -eq 0 -and $pip.output -match '^pip\s+\d') {
        Add-Check 'pip' 'OK' $pip.output
    } else {
        Add-Check 'pip' 'ERROR' $pip.error 'Восстановите pip: py -3.12 -m ensurepip --upgrade. Затем создайте .venv заново или установите pip в нужное окружение.'
    }
    $venv = Invoke-Probe $pythonInfo.executable @('-c', 'import venv,ensurepip; print("venv and ensurepip available")')
    if ($venv.exitCode -eq 0) {
        Add-Check 'venv / ensurepip' 'OK' 'Модули для создания окружения доступны.'
    } else {
        Add-Check 'venv / ensurepip' 'ERROR' $venv.error 'Восстановите установку Python с компонентами pip и venv. README: раздел 1.3.'
    }
} else {
    Add-Check 'Python 3.12 x64' 'ERROR' $pythonFailure $pythonInstall
    Add-Check 'pip / venv' 'SKIP' 'Сначала нужен рабочий Python.'
}

$nodePath = Find-Tool @('node.exe', 'node')
if ($nodePath) {
    $node = Invoke-Probe $nodePath @('--version')
    if ($node.exitCode -eq 0 -and $node.output -match '^v?(\d+)\.(\d+)\.(\d+)') {
        $major, $minor = [int]$Matches[1], [int]$Matches[2]
        if ($major -ge 22 -or ($major -eq 20 -and $minor -ge 19)) {
            Add-Check 'Node.js' 'OK' "$($node.output); $nodePath"
        } else {
            Add-Check 'Node.js' 'ERROR' "Найден $($node.output); для проекта нужен 22+ или 20.19+." $nodeInstall
        }
    } else { Add-Check 'Node.js' 'ERROR' "Не удалось получить версию: $($node.error)" $nodeInstall }
} else { Add-Check 'Node.js' 'ERROR' 'Команда node не найдена в PATH.' $nodeInstall }

$npmPath = Find-Tool @('npm.cmd', 'npm')
if ($npmPath) {
    $npm = Invoke-Probe $npmPath @('--version')
    if ($npm.exitCode -eq 0 -and $npm.output -match '^(\d+)\.\d+\.\d+') {
        if ([int]$Matches[1] -ge 9) {
            Add-Check 'npm 9+' 'OK' "$($npm.output); $npmPath"
        } else { Add-Check 'npm 9+' 'ERROR' "Найден npm $($npm.output)." $nodeInstall }
    } else { Add-Check 'npm 9+' 'ERROR' "Не удалось получить версию: $($npm.error)" $nodeInstall }
} else { Add-Check 'npm 9+' 'ERROR' 'npm не найден. Он устанавливается вместе с Node.js.' $nodeInstall }

if (Find-Tool @('git.exe', 'git')) {
    Add-Check 'Git (необязателен)' 'OK' 'Найден в PATH.'
} else {
    Add-Check 'Git (необязателен)' 'WARN' 'Не найден; проект можно скачать ZIP-архивом.' 'Для git clone: winget install --exact --id Git.Git. Или https://git-scm.com/downloads/win'
}

if ($Project) {
    if (Test-Path -LiteralPath (Join-Path $projectRoot '.venv\Scripts\python.exe') -PathType Leaf) {
        Add-Check '.venv' 'OK' 'Окружение проекта существует.'
    } else { Add-Check '.venv' 'ERROR' 'Окружение проекта не создано.' 'В корне проекта: py -3.12 -m venv .venv' }
    if ($pythonInfo) {
        $packageCode = @'
import importlib.metadata as metadata,json,pathlib,re
errors=[]
for line in pathlib.Path('requirements.txt').read_text(encoding='utf-8').splitlines():
    match=re.match(r'([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^;\s]+)',line)
    if not match: continue
    name,wanted=match.groups()
    try:
        actual=metadata.version(name)
        if actual!=wanted: errors.append(name+': '+actual+' (нужно '+wanted+')')
    except metadata.PackageNotFoundError: errors.append(name+': не установлен')
print(json.dumps(dict(missing=errors),ensure_ascii=True))
'@
        $packages = Invoke-Probe $pythonInfo.executable @('-c', $packageCode)
        try {
            if ($packages.exitCode -ne 0) { throw $packages.error }
            $packageReport = $packages.output | ConvertFrom-Json
            $missing = @($packageReport.missing)
            if ($missing.Count) {
                Add-Check 'Python-пакеты проекта' 'ERROR' ($missing -join '; ') '.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt'
            } else { Add-Check 'Python-пакеты проекта' 'OK' 'Версии соответствуют requirements.txt.' }
        } catch { Add-Check 'Python-пакеты проекта' 'ERROR' $_.Exception.Message 'Установите зависимости из requirements.txt в .venv.' }
        $pipCheck = Invoke-Probe $pythonInfo.executable @('-m', 'pip', 'check')
        if ($pipCheck.exitCode -eq 0) { Add-Check 'Совместимость Python-пакетов' 'OK' $pipCheck.output }
        else { Add-Check 'Совместимость Python-пакетов' 'ERROR' ($pipCheck.output + ' ' + $pipCheck.error) 'Повторите установку с -r requirements.txt -c constraints.txt.' }
        $imports = Invoke-Probe $pythonInfo.executable @('-c', 'import fastapi,uvicorn,sqlalchemy,psycopg,multipart,pymupdf,docx,openpyxl,PIL,pytesseract,cv2,numpy,tesserocr; print("Imports OK")')
        if ($imports.exitCode -eq 0) { Add-Check 'Импорт библиотек / DLL' 'OK' 'Библиотеки приложения загружаются.' }
        else { Add-Check 'Импорт библиотек / DLL' 'ERROR' $imports.error 'Проверьте Python 3.12 x64 и повторите установку requirements.txt. Полный текст ошибки указан выше.' }
        $ocrCode = "import os,pathlib,tesserocr; path=os.getenv('TESSDATA_PREFIX',str(pathlib.Path.cwd()/'.runtime'/'tessdata')); api=tesserocr.PyTessBaseAPI(path=path,lang='rus+eng'); api.End(); print('rus+eng OK')"
        $ocr = Invoke-Probe $pythonInfo.executable @('-c', $ocrCode)
        if ($ocr.exitCode -eq 0) { Add-Check 'OCR rus + eng' 'OK' 'Tesseract загрузил оба языковых пакета.' }
        else { Add-Check 'OCR rus + eng' 'ERROR' $ocr.error '.\.venv\Scripts\python.exe scripts/setup_ocr.py' }
    } else { Add-Check 'Пакеты и OCR проекта' 'SKIP' 'Проверка доступна после установки Python.' }
    if (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html') -PathType Leaf) {
        Add-Check 'Сборка интерфейса' 'OK' 'frontend/dist/index.html существует; start.ps1 проверит актуальность и при необходимости пересоберёт интерфейс.'
    } else { Add-Check 'Сборка интерфейса' 'ERROR' 'Готовый интерфейс не найден.' 'В frontend выполните npm.cmd ci, затем npm.cmd run build.' }
}

$errors = @($checks | Where-Object { $_.status -eq 'ERROR' }).Count
$warnings = @($checks | Where-Object { $_.status -eq 'WARN' }).Count
if ($Json) {
    [pscustomobject]@{ scope = $(if ($Project) { 'project' } else { 'tools' }); ready = ($errors -eq 0); errors = $errors; warnings = $warnings; checks = @($checks.ToArray()) } | ConvertTo-Json -Depth 5
} else {
    Write-Host 'Проверка зависимостей Сверки для Windows (без Docker)'
    Write-Host "Каталог проекта: $projectRoot"
    Write-Host ''
    foreach ($check in $checks) {
        Write-Host "[$($check.status)] $($check.name): $($check.detail)"
        if ($check.hint) { Write-Host "  Что сделать: $($check.hint)" }
    }
    Write-Host ''
    if ($errors) { Write-Host "Нужно исправить ошибок: $errors. Инструкции по установке: README.md, раздел 1.3." }
    elseif ($Project) { Write-Host 'Окружение готово к запуску. Следующий шаг: scripts/start.ps1.' }
    else { Write-Host 'Системные инструменты готовы. Следующий шаг: установка проекта по README.md, разделы 1.4-1.7.' }
}
if ($errors) { exit 1 }
exit 0
