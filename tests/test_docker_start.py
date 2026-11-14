import json
import subprocess

import pytest

from scripts import start_docker, setup_xiaomi_ocr


class Docker:
    def __init__(self, gpu=True, device='auto', broken_image=False):
        self.gpu, self.device, self.broken_image = gpu, device, broken_image
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs['env'].copy()))
        stdout, stderr, code = '', '', 0
        if command[1] == 'info':
            stdout = 'linux\n'
        elif 'config' in command:
            stdout = json.dumps({'services': {'api': {'image': 'test-ocr:local', 'environment': {
                'OCR_PROVIDER': 'xiaomi', 'XIAOMI_OCR_DEVICE': self.device}}}})
        elif command[1] == 'run':
            if self.broken_image:
                code, stdout = 2, json.dumps({'available': False, 'reason': 'No module named torch'})
            elif '--gpus' in command and not self.gpu:
                code, stderr = 125, "could not select device driver nvidia with capabilities: [[gpu]]\n\nRun 'docker run --help' for more information"
            else:
                stdout = json.dumps({'available': True, 'device': command[-1], 'name': 'Test GPU' if '--gpus' in command else 'CPU'})
        return subprocess.CompletedProcess(command, code, stdout, stderr)


@pytest.mark.parametrize(('gpu', 'selected'), [(True, 'cuda'), (False, 'cpu')])
def test_auto_uses_container_gpu_probe_and_preserves_local_settings(tmp_path, monkeypatch, capsys, gpu, selected):
    fake = Docker(gpu=gpu)
    monkeypatch.setattr(start_docker, 'ROOT', tmp_path)
    monkeypatch.setattr(start_docker.subprocess, 'run', fake)
    monkeypatch.setenv('OCR_PROVIDER', 'tesseract')
    monkeypatch.setenv('XIAOMI_OCR_DEVICE', 'cuda')
    env_file = tmp_path/'.env'
    env_file.write_text('AUTH_MODE=local\nPOSTGRES_PASSWORD=keep\nXIAOMI_OCR_DEVICE=cuda\n', encoding='utf-8')
    original = env_file.read_bytes()
    start_docker.main([])
    up, env = next((cmd, env) for cmd, env in fake.calls if 'up' in cmd)
    assert env['DOCKER_OCR_DEVICE'] == selected
    assert any(arg.endswith('compose.gpu.yaml') for arg in up) == gpu
    assert env_file.read_bytes() == original
    assert all(env['XIAOMI_OCR_DEVICE'] == 'cuda' for _, env in fake.calls)
    assert next(i for i, (cmd, _) in enumerate(fake.calls) if 'build' in cmd) < next(i for i, (cmd, _) in enumerate(fake.calls) if cmd[1] == 'run')
    assert next(i for i, (cmd, _) in enumerate(fake.calls) if 'model-init' in cmd) < next(i for i, (cmd, _) in enumerate(fake.calls) if 'up' in cmd)
    state = json.loads((tmp_path/'.runtime/docker-start.json').read_text(encoding='utf-8'))
    assert state['device'] == selected and state['provider'] == 'xiaomi'
    assert 'POSTGRES_PASSWORD' not in json.dumps(state)
    if not gpu:
        assert 'could not select device driver' in capsys.readouterr().out


def test_forced_cpu_never_requests_a_gpu_and_can_reuse_the_image(tmp_path, monkeypatch):
    fake = Docker()
    monkeypatch.setattr(start_docker, 'ROOT', tmp_path)
    monkeypatch.setattr(start_docker.subprocess, 'run', fake)
    start_docker.main(['--device', 'cpu', '--no-build'])
    assert not any('--gpus' in cmd or 'build' in cmd for cmd, _ in fake.calls)
    assert next(env for cmd, env in fake.calls if 'up' in cmd)['DOCKER_OCR_DEVICE'] == 'cpu'


def test_explicit_gpu_requirement_fails_before_starting_services(tmp_path, monkeypatch):
    fake = Docker(gpu=False)
    monkeypatch.setattr(start_docker, 'ROOT', tmp_path)
    monkeypatch.setattr(start_docker.subprocess, 'run', fake)
    with pytest.raises(SystemExit) as error:
        start_docker.main(['--device', 'cuda', '--no-build'])
    assert error.value.code == 1
    assert not any('up' in cmd or 'model-init' in cmd for cmd, _ in fake.calls)


def test_broken_image_is_reported_instead_of_claiming_a_cpu_fallback(tmp_path, monkeypatch):
    fake = Docker(broken_image=True)
    monkeypatch.setattr(start_docker, 'ROOT', tmp_path)
    monkeypatch.setattr(start_docker.subprocess, 'run', fake)
    with pytest.raises(SystemExit):
        start_docker.main(['--no-build'])
    assert not any('up' in cmd for cmd, _ in fake.calls)


def test_probe_timeout_removes_only_its_own_container(monkeypatch):
    calls = []
    def execute(command, *args, **kwargs):
        calls.append(command)
        if command[1] == 'run':
            raise subprocess.TimeoutExpired(command, 90)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(start_docker, 'execute', execute)
    available, _ = start_docker.probe('test:local', 'cuda', {})
    assert not available
    name = calls[0][calls[0].index('--name')+1]
    assert name.startswith('sverka-ocr-probe-') and calls[1] == ['docker', 'rm', '-f', name]


def test_prepared_weights_are_reused_offline_without_changing_env(tmp_path, monkeypatch):
    model = tmp_path/'model'
    model.mkdir()
    for name in setup_xiaomi_ocr.MODEL_FILES:
        (model/name).write_bytes(b'prepared')
    (model/'sverka-model.json').write_text(json.dumps({'model': setup_xiaomi_ocr.MODEL_ID,
                                                   'revision': setup_xiaomi_ocr.MODEL_REVISION}), encoding='utf-8')
    assert setup_xiaomi_ocr.prepared_model(model)
    env_file = tmp_path/'.env'
    env_file.write_text('AUTH_MODE=local\nOCR_PROVIDER=tesseract\n', encoding='utf-8')
    before = env_file.read_bytes()
    setup_xiaomi_ocr.main(['--download-only', '--if-missing', '--model-dir', str(model), '--env-file', str(env_file)])
    assert env_file.read_bytes() == before
    (model/'tokenizer.json').unlink()
    assert not setup_xiaomi_ocr.prepared_model(model)


def test_an_unpinned_or_incomplete_model_is_not_mistaken_for_a_ready_one(tmp_path):
    (tmp_path/'sverka-model.json').write_text('{"revision":"other"}', encoding='utf-8')
    assert not setup_xiaomi_ocr.prepared_model(tmp_path)
