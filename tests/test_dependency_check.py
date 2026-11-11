"""The Windows bootstrap check must also work before Python/Node are installed."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell bootstrap script')
ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'


def run_check(folder, python_exe):
    env = dict(os.environ, PATH=str(folder))
    result = subprocess.run(
        [str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(ROOT/'scripts/check_dependencies.ps1'), '-Json', '-PythonExe', str(python_exe)],
        cwd=folder, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60,
    )
    assert not result.stderr, result.stderr
    report = json.loads(result.stdout)
    return result.returncode, report, {check['name']: check for check in report['checks']}


@pytest.mark.parametrize(('node', 'npm', 'ready'), [
    ('20.19.0', '9.0.0', True),
    ('22.0.0', '10.0.0', True),
    ('18.20.8', '8.19.4', False),
])
def test_supported_and_old_tool_versions(tmp_path, node, npm, ready):
    (tmp_path/'node.cmd').write_text('@echo off\necho v'+node+'\n', encoding='ascii')
    (tmp_path/'npm.cmd').write_text('@echo off\necho '+npm+'\n', encoding='ascii')
    code, report, checks = run_check(tmp_path, sys.executable)
    assert report['ready'] is ready
    assert code == (0 if ready else 1)
    assert checks['Git (необязателен)']['status'] == 'WARN'
    assert checks['Python 3.12 x64']['status'] == 'OK'
    assert checks['Node.js']['status'] == ('OK' if ready else 'ERROR')
    assert checks['npm 9+']['status'] == ('OK' if ready else 'ERROR')
    if not ready:
        assert 'OpenJS.NodeJS.LTS' in checks['Node.js']['hint']


def test_no_python_or_node_reports_installation_steps(tmp_path):
    code, report, checks = run_check(tmp_path, tmp_path/'missing-python.exe')
    assert code == 1
    assert report['ready'] is False
    assert report['errors'] == 3
    assert checks['pip / venv']['status'] == 'SKIP'
    assert 'Python.Python.3.12' in checks['Python 3.12 x64']['hint']
    assert 'OpenJS.NodeJS.LTS' in checks['npm 9+']['hint']


def test_wrong_python_version_and_architecture_are_detected(tmp_path):
    details = json.dumps({'version': [3, 11, 9], 'bits': 32, 'executable': sys.executable})
    fake_python = tmp_path/'python.cmd'
    fake_python.write_text('@echo off\necho '+details+'\n', encoding='ascii')
    code, report, checks = run_check(tmp_path, fake_python)
    assert code == 1
    assert report['ready'] is False
    assert checks['Python 3.12 x64']['status'] == 'ERROR'
    assert '3.11.9, 32-bit' in checks['Python 3.12 x64']['detail']
