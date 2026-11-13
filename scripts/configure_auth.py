"""Configure the shared password without printing or storing it as plaintext."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.auth_passwords import password_hash


def save_settings(path: Path, encoded: str, secure: bool):
    values = {'AUTH_PASSWORD_HASH': encoded, 'AUTH_COOKIE_SECURE': str(secure).lower()}
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


def main():
    parser = argparse.ArgumentParser(description='Настроить пароль входа в Сверку (не менее 12 символов).')
    parser.add_argument('--http', action='store_true', help='Разрешить cookie без HTTPS для localhost / SSH-туннеля.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    args = parser.parse_args()
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
    save_settings(args.env_file.resolve(), encoded, secure=not args.http)
    print('Настройки входа сохранены. Перезапустите приложение. Старые сессии будут завершены.')


if __name__ == '__main__':
    main()
