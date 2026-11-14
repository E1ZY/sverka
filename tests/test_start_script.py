"""Exercise the Windows launcher without starting a real server or invoking npm."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell launcher')
ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'


@pytest.fixture
def project(tmp_path):
    # Spaces and Cyrillic also exercise native command/path handling in PowerShell 5.1.
    folder = tmp_path/'проект с пробелами'
    (folder/'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT/'scripts/start.ps1', folder/'scripts/start.ps1')
    shutil.copyfile(ROOT/'scripts/configure_auth.py', folder/'scripts/configure_auth.py')
    (folder/'app').mkdir()
    (folder/'app/__init__.py').touch()
    for name in ['auth_config.py', 'auth_passwords.py']:
        shutil.copyfile(ROOT/'app'/name, folder/'app'/name)
    (folder/'.env').write_text('AUTH_MODE=local\nBIND_ADDRESS=127.0.0.1\n', encoding='utf-8')
    subprocess.run(
        [sys.executable, '-m', 'venv', '--without-pip', str(folder/'.venv')],
        check=True, capture_output=True, timeout=30,
    )
    frontend = folder/'frontend'
    (frontend/'src').mkdir(parents=True)
    (frontend/'public').mkdir()
    (frontend/'node_modules').mkdir()
    (frontend/'src/main.tsx').write_text('export const version = 1;', encoding='utf-8')
    (frontend/'src/extra.ts').write_text('export {};', encoding='utf-8')
    (frontend/'public/logo.svg').write_text('<svg/>', encoding='utf-8')
    (frontend/'package.json').write_text('{}', encoding='utf-8')
    (frontend/'package-lock.json').write_text('{}', encoding='utf-8')
    (frontend/'vite.config.ts').write_text('export default {};', encoding='utf-8')
    (frontend/'tsconfig.json').write_text('{}', encoding='utf-8')
    (frontend/'index.html').write_text('<div id="root"></div>', encoding='utf-8')
    tools = folder/'tools'
    tools.mkdir()
    (tools/'npm.cmd').write_text(
        '@echo off\n'
        'if not "%~1"=="run" exit /b 31\n'
        'if not "%~2"=="build" exit /b 32\n'
        'echo build>>"%SVERKA_START_LOG%"\n'
        'if "%SVERKA_SKIP_OUTPUT%"=="1" exit /b 0\n'
        'if not exist dist mkdir dist\n'
        'echo built>dist\\index.html\n'
        'if "%SVERKA_FAIL_BUILD%"=="1" (\n'
        '  echo partial>dist\\index.html\n'
        '  exit /b 17\n'
        ')\n'
        'exit /b 0\n', encoding='ascii',
    )
    (folder/'uvicorn.py').write_text(
        'import os, pathlib, sys\n'
        'assert sys.argv[1:] == ["app.main:app", "--host", "127.0.0.1", "--port", "8000"]\n'
        'with pathlib.Path(os.environ["SVERKA_START_LOG"]).open("a", encoding="utf-8") as log:\n'
        '    log.write("server\\n")\n'
        'sys.exit(int(os.environ.get("SVERKA_SERVER_EXIT", "0")))\n',
        encoding='utf-8',
    )
    env = dict(os.environ, PATH=str(tools), SVERKA_START_LOG=str(folder/'calls.log'), AUTH_MODE='local',
               AUTH_PASSWORD_HASH='', BIND_ADDRESS='127.0.0.1', AUTH_LOCAL_PROXY='false')
    return folder, env


def run_start(project, **overrides):
    folder, env = project
    log = folder/'calls.log'
    log.unlink(missing_ok=True)
    result = subprocess.run(
        [str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(folder/'scripts/start.ps1')],
        # The launcher must find its project even when called from another directory.
        cwd=folder.parent, env=dict(env, **overrides), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=40,
    )
    calls = log.read_text(encoding='utf-8').splitlines() if log.exists() else []
    return result, calls


def assert_started(result, calls, *, build):
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == (['build', 'server'] if build else ['server'])


def test_first_start_builds_and_unchanged_start_needs_no_npm(project):
    assert_started(*run_start(project), build=True)
    folder, _ = project
    state = json.loads((folder/'frontend/dist/.sverka-build.json').read_text(encoding='utf-8'))
    assert state['version'] == 1
    # Compiler cache and timestamp-only changes are not source edits.
    (folder/'frontend/tsconfig.tsbuildinfo').write_text('new compiler cache', encoding='utf-8')
    os.utime(folder/'frontend/src/main.tsx', (1, 1))
    assert_started(*run_start(project, PATH=str(folder/'no-npm')), build=False)


def test_unconfigured_access_stops_before_build_without_interactive_terminal(project):
    folder, _ = project
    (folder/'.env').unlink()
    result, calls = run_start(project, AUTH_MODE='password', AUTH_PASSWORD_HASH='')
    assert result.returncode != 0
    assert calls == []
    assert '--mode local' in result.stderr, result.stderr


@pytest.mark.parametrize('change', [
    'source', 'add', 'delete', 'rename', 'config', 'lockfile', 'public', 'env',
])
def test_changed_inputs_rebuild_even_with_preserved_timestamp(project, change):
    assert_started(*run_start(project), build=True)
    folder, _ = project
    frontend = folder/'frontend'
    if change == 'source':
        path = frontend/'src/main.tsx'
    elif change == 'add':
        path = frontend/'src/added.ts'
    elif change == 'delete':
        (frontend/'src/extra.ts').unlink()
        path = None
    elif change == 'rename':
        (frontend/'src/extra.ts').rename(frontend/'src/renamed.ts')
        path = None
    else:
        path = frontend/{
            'config': 'vite.config.ts', 'lockfile': 'package-lock.json',
            'public': 'public/logo.svg', 'env': '.env.production',
        }[change]
    if path is not None:
        previous = path.stat() if path.exists() else None
        path.write_text('changed', encoding='utf-8')
        if previous:
            os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert_started(*run_start(project), build=True)
    assert_started(*run_start(project), build=False)


@pytest.mark.parametrize('damage', ['missing-index', 'changed-output', 'missing-state', 'invalid-state'])
def test_missing_or_damaged_build_is_rebuilt(project, damage):
    assert_started(*run_start(project), build=True)
    folder, _ = project
    output = folder/'frontend/dist'
    if damage == 'missing-index':
        (output/'index.html').unlink()
    elif damage == 'changed-output':
        (output/'index.html').write_text('replaced by another build', encoding='utf-8')
    elif damage == 'missing-state':
        (output/'.sverka-build.json').unlink()
    else:
        (output/'.sverka-build.json').write_text('{invalid', encoding='utf-8')
    assert_started(*run_start(project), build=True)


def test_failed_build_never_starts_server_or_preserves_success_stamp(project):
    assert_started(*run_start(project), build=True)
    folder, _ = project
    source = folder/'frontend/src/main.tsx'
    original = source.read_bytes()
    source.write_text('changed', encoding='utf-8')
    result, calls = run_start(project, SVERKA_FAIL_BUILD='1')
    assert result.returncode != 0
    assert calls == ['build']
    assert not (folder/'frontend/dist/.sverka-build.json').exists()
    # Even reverting the edit must not reuse the failed, partially written output.
    source.write_bytes(original)
    assert_started(*run_start(project), build=True)


def test_success_without_bundle_does_not_start_server(project):
    result, calls = run_start(project, SVERKA_SKIP_OUTPUT='1')
    assert result.returncode != 0
    assert calls == ['build']


def test_missing_node_dependencies_give_install_hint(project):
    folder, _ = project
    (folder/'frontend/node_modules').rmdir()
    result, calls = run_start(project)
    assert result.returncode != 0
    assert calls == []
    assert 'npm.cmd ci' in result.stderr


def test_missing_npm_gives_install_hint(project):
    folder, _ = project
    result, calls = run_start(project, PATH=str(folder/'no-npm'))
    assert result.returncode != 0
    assert calls == []
    assert 'Node.js' in result.stderr


def test_server_exit_code_is_preserved(project):
    result, calls = run_start(project, SVERKA_SERVER_EXIT='7')
    assert result.returncode == 7
    assert calls == ['build', 'server']


def break_base_python(folder):
    config = folder/'.venv/pyvenv.cfg'
    missing_home = folder/'removed base python'
    lines = config.read_text(encoding='utf-8').splitlines()
    config.write_text('\n'.join(
        'home = '+str(missing_home) if line.startswith('home =') else
        'executable = '+str(missing_home/'python.exe') if line.startswith('executable =') else line
        for line in lines
    )+'\n', encoding='utf-8')


@pytest.mark.parametrize('already_built', [False, True])
def test_removed_base_python_stops_before_frontend_and_explains_repair(project, already_built):
    if already_built:
        assert_started(*run_start(project), build=True)
    folder, _ = project
    break_base_python(folder)
    result, calls = run_start(project)
    assert result.returncode != 0
    assert calls == []
    assert '.venv' in result.stderr and 'pyvenv.cfg' in result.stderr
    assert 'py -3.12 -m venv --upgrade .venv' in result.stderr


def test_non_venv_python_is_not_silently_used(project):
    folder, _ = project
    site = folder/'.venv/Lib/site-packages'
    (site/'sitecustomize.py').write_text('import sys\nsys.prefix = sys.base_prefix\n', encoding='utf-8')
    result, calls = run_start(project)
    assert result.returncode != 0
    assert calls == []
    assert '.venv' in result.stderr


def test_missing_venv_python_stops_without_build_or_server(project):
    folder, _ = project
    (folder/'.venv/Scripts/python.exe').unlink()
    result, calls = run_start(project)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize('broken', [False, True])
def test_project_diagnostics_inspect_venv_even_with_global_python_override(project, broken):
    folder, env = project
    script = folder/'scripts/check_dependencies.ps1'
    shutil.copyfile(ROOT/'scripts/check_dependencies.ps1', script)
    (folder/'requirements.txt').write_text('fastapi==0.162.4\n', encoding='utf-8')
    if broken:
        break_base_python(folder)
    result = subprocess.run(
        [str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(script), '-Project', '-Json', '-PythonExe', sys.executable],
        cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8', timeout=40,
    )
    assert not result.stderr, result.stderr
    report = json.loads(result.stdout)
    checks = {check['name']: check for check in report['checks']}
    assert checks['.venv']['status'] == ('ERROR' if broken else 'OK')
    assert not report['ready']
    if broken:
        assert checks['Пакеты и OCR проекта']['status'] == 'SKIP'
        assert 'pyvenv.cfg' in checks['.venv']['hint']
    else:
        # The global test interpreter has FastAPI; the isolated fixture venv does not.
        assert checks['Python-пакеты проекта']['status'] == 'ERROR'
        assert 'fastapi' in checks['Python-пакеты проекта']['detail']
