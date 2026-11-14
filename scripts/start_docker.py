"""Optional host GPU probe and Compose launcher. Plain Compose supports a per-host override."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
PROBE = '''import json, sys
try:
    import torch
    device = sys.argv[1]
    info = {"torch": torch.__version__, "compiled_cuda": torch.version.cuda}
    if device == "cuda" and not torch.cuda.is_available():
        print(json.dumps({**info, "available": False, "reason": "CUDA недоступна в контейнере"}))
        sys.exit(3)
    value = torch.ones(1, device=device).sum().item()
    print(json.dumps({**info, "available": value == 1, "device": device,
                      "name": torch.cuda.get_device_name(0) if device == "cuda" else "CPU"}))
except Exception as error:
    print(json.dumps({"available": False, "reason": str(error)}))
    sys.exit(2)
'''


def execute(command, env, *, capture=False, timeout=None):
    return subprocess.run(command, cwd=ROOT, env=env, text=True, encoding='utf-8', errors='replace',
                          capture_output=capture, timeout=timeout)


def checked(command, env, *, capture=False, timeout=None):
    result = execute(command, env, capture=capture, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Команда Docker завершилась ошибкой. Проверьте сообщение выше и настройки по разделу 2 README.')
    return result


def probe(image, device, env):
    name = 'sverka-ocr-probe-' + uuid4().hex
    command = ['docker', 'run', '--rm', '--pull=never', '--name', name, '--network=none']
    if device == 'cuda':
        command += ['--gpus', 'all']
    command += ['--entrypoint', 'python', image, '-c', PROBE, device]
    try:
        result = execute(command, env, capture=True, timeout=90)
    except subprocess.TimeoutExpired:
        execute(['docker', 'rm', '-f', name], env, capture=True, timeout=30)
        return False, {'reason': 'Проверка устройства в контейнере превысила 90 секунд.'}
    try:
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        lines = [line.strip() for line in result.stderr.splitlines() if line.strip() and not line.startswith("Run 'docker")]
        info = {'reason': (lines or ['Контейнер проверки не запустился.'])[0][:500]}
    else:
        if result.returncode and result.stderr.strip():
            info['reason'] = (info.get('reason', '') + ' ' + result.stderr.strip())[:1000]
    return result.returncode == 0 and info.get('available') is True, info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['auto', 'cuda', 'cpu'], help='По умолчанию DOCKER_OCR_DEVICE или auto.')
    parser.add_argument('--no-build', action='store_true', help='Использовать уже собранный образ.')
    args = parser.parse_args(argv)
    env = os.environ.copy()
    base = ['docker', 'compose', '--project-directory', str(ROOT), '-f', str(ROOT/'compose.yaml')]
    try:
        daemon = execute(['docker', 'info', '--format', '{{.OSType}}'], env, capture=True, timeout=30)
        if daemon.returncode or daemon.stdout.strip() != 'linux':
            raise RuntimeError('Недоступен Docker Engine с Linux-контейнерами. Запустите Docker и проверьте docker info.')
        config_result = execute(base + ['config', '--format', 'json'], env, capture=True, timeout=30)
        if config_result.returncode:
            raise RuntimeError('Не удалось прочитать Compose. Выполните docker compose config --quiet и исправьте настройки .env.')
        config = json.loads(config_result.stdout)
        settings = config['services']['api']['environment']
        requested = args.device or settings.get('XIAOMI_OCR_DEVICE', 'auto')
        if requested not in ('auto', 'cuda', 'cpu'):
            raise RuntimeError('DOCKER_OCR_DEVICE: используйте auto, cuda или cpu.')
        image = config['services']['api']['image']
        if not args.no_build:
            checked(base + ['build', 'api'], env)
        ready, cpu_info = probe(image, 'cpu', env)
        if not ready:
            raise RuntimeError('Не удалось проверить PyTorch в образе: ' + cpu_info.get('reason', 'неизвестная ошибка')
                               + ' Соберите образ запуском без --no-build.')
        selected, info = 'cpu', cpu_info
        if requested != 'cpu' and settings.get('OCR_PROVIDER') == 'xiaomi':
            available, gpu_info = probe(image, 'cuda', env)
            if available:
                selected, info = 'cuda', gpu_info
            elif requested == 'cuda':
                raise RuntimeError('GPU запрошена явно, но недоступна: ' + gpu_info.get('reason', 'ошибка CUDA'))
            else:
                print('GPU недоступна в Docker; Xiaomi OCR будет работать на CPU. '
                      + gpu_info.get('reason', ''), flush=True)
        env['DOCKER_OCR_DEVICE'] = selected
        command = base + (['-f', str(ROOT/'compose.gpu.yaml')] if selected == 'cuda' else [])
        print(f'OCR: {settings.get("OCR_PROVIDER")}; устройство: {selected}; {info.get("name", "CPU")}.', flush=True)
        (ROOT/'.runtime/models').mkdir(parents=True, exist_ok=True)
        print('Подготовка модели (веса сохраняются в .runtime/models)…', flush=True)
        checked(command + ['run', '--rm', '--no-deps', 'model-init'], env)
        checked(command + ['up', '-d', '--wait', '--wait-timeout', '180', '--no-build'], env)
        checked(command + ['ps'], env)
        state = {'started_at': datetime.now(timezone.utc).isoformat(),
                 'device': selected, 'provider': settings.get('OCR_PROVIDER'), 'image': image,
                 'probe': info, 'compose_files': ['compose.yaml'] + (['compose.gpu.yaml'] if selected == 'cuda' else [])}
        (ROOT/'.runtime/docker-start.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Готово. Откройте http://127.0.0.1:8000. Режим запуска: .runtime/docker-start.json', flush=True)
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError) as error:
        parser.exit(1, f'Запуск Docker не выполнен: {error}\n')


if __name__ == '__main__':
    main()
