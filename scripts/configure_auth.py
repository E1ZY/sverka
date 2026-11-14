"""Choose local access or configure the shared password using only stdlib."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.auth_passwords import password_hash
from app.auth_config import AuthSettings


def save_settings(path: Path, encoded: str, secure: bool, mode: str = 'password'):
    AuthSettings(encoded, secure, mode)  # Validate before replacing any settings.
    values = {'AUTH_MODE': mode, 'AUTH_PASSWORD_HASH': encoded, 'AUTH_COOKIE_SECURE': str(secure).lower()}
    if mode == 'local':
        # Explicitly selecting local mode also restores a local Docker binding.
        values.update(AUTH_PASSWORD_HASH='', AUTH_COOKIE_SECURE='false', BIND_ADDRESS='127.0.0.1')
    lines = path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    # Preserve PostgreSQL credentials and unrelated local settings verbatim.
    lines = [line for line in lines if line.partition('=')[0].strip() not in values]
    content = '\n'.join([*lines, *(f'{key}={value}' for key, value in values.items()), ''])
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        if os.name == 'posix':
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Выбрать режим Сверки: локально без входа или с общим паролем.')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--mode', choices=['local', 'password'], help='local — без входа на localhost; password — общий пароль.')
    selection.add_argument('--ensure', action='store_true', help='Сохранить настроенный режим; предложить выбор, если доступа ещё нет.')
    parser.add_argument('--http', action='store_true', help='Разрешить cookie без HTTPS для localhost / SSH-туннеля.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    args = parser.parse_args(argv)
    path = args.env_file.resolve()
    if args.ensure:
        try:
            settings = AuthSettings.from_env(path)
        except ValueError as error:
            parser.error(f'{error} Исправьте .env или запустите scripts/configure_auth.py --mode local / --mode password.')
        if settings.mode == 'local' or settings.password_hash:
            print('Режим доступа: ' + ('локальный, без авторизации (localhost).' if settings.mode == 'local' else 'с общим паролем.'))
            return
    mode = args.mode
    if mode is None:
        if not sys.stdin.isatty():
            parser.error('Режим доступа ещё не настроен. В терминале запустите scripts/configure_auth.py --mode local или --mode password --http, затем повторите запуск.')
        print('Выберите режим доступа к Сверке:\n  1 — без авторизации, для локальной разработки (localhost)\n  2 — с общим паролем (для совместной работы)')
        try:
            choice = input('Режим [1/2, по умолчанию 2]: ').strip() or '2'
        except (EOFError, KeyboardInterrupt):
            parser.error('Выбор прерван. Настройки не изменены. Повторите в терминале или задайте --mode local / --mode password --http.')
        if choice not in {'1', '2'}:
            parser.error('Введите 1 или 2. Настройки не изменены.')
        mode = 'local' if choice == '1' else 'password'
    if mode == 'local':
        save_settings(path, '', False, mode='local')
        print('Включён локальный режим без авторизации. Открывайте http://127.0.0.1:8000. Перезапустите приложение, если оно уже работает.')
        return
    if args.http:
        print('HTTP-режим: используйте localhost, SSH-туннель или закрытую тестовую сеть. Пароль не шифрует HTTP-трафик.')
    first = getpass.getpass('Пароль доступа: ')
    second = getpass.getpass('Повторите пароль: ')
    if first != second:
        parser.error('Пароли не совпадают. Настройки не изменены.')
    try:
        encoded = password_hash(first)
    except ValueError as error:
        parser.error(str(error))
    save_settings(path, encoded, secure=not args.http, mode='password')
    print('Настройки входа сохранены. Перезапустите приложение. Старые сессии будут завершены.')


if __name__ == '__main__':
    main()
