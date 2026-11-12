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
    env = dict(os.environ, PATH=str(tools), SVERKA_START_LOG=str(folder/'calls.log'))
    return folder, env


def run_start(project, **overrides):
    folder, env = project
    log = folder/'calls.log'
    log.unlink(missing_ok=True)
    result = subprocess.run(
        [str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(folder/'scripts/start.ps1')],
        # The launcher must find its project even when called from another directory.
        cwd=folder.parent, env=dict(env, **overrides), capture_output=True,
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
