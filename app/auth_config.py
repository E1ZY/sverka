"""Authentication configuration shared by the server and the stdlib-only installer."""
import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from .auth_passwords import parse_hash

ROOT = Path(__file__).resolve().parent.parent
KEYS = {'AUTH_MODE', 'AUTH_PASSWORD_HASH', 'AUTH_COOKIE_SECURE', 'AUTH_LOCAL_PROXY', 'BIND_ADDRESS'}


def is_loopback(host: str) -> bool:
    if host.lower() == 'localhost':
        return True
    try:
        address = ipaddress.ip_address(host)
        return (address.ipv4_mapped or address).is_loopback if address.version == 6 else address.is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class AuthSettings:
    password_hash: str = ''
    cookie_secure: bool = True
    mode: str = 'password'
    local_proxy: bool = False
    bind_address: str = '127.0.0.1'

    def __post_init__(self):
        if self.mode not in {'password', 'local'}:
            raise ValueError('AUTH_MODE должен быть password или local.')
        if self.password_hash:
            parse_hash(self.password_hash)
        if self.mode == 'local' and not is_loopback(self.bind_address):
            raise ValueError('Режим без авторизации требует BIND_ADDRESS=127.0.0.1. Для сетевого доступа выберите режим password.')

    @classmethod
    def from_env(cls, path: Path | None = None):
        values = {}
        path = path if path is not None else ROOT / '.env'
        if path.is_file():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                if sep and key.strip() in KEYS:
                    values[key.strip()] = value.strip().strip('\"\'')
        values.update({key: os.environ[key] for key in KEYS if key in os.environ})

        def boolean(key, default):
            value = values.get(key, default).lower()
            if value not in {'true', 'false'}:
                raise ValueError(f'{key} должен быть true или false.')
            return value == 'true'

        return cls(password_hash=values.get('AUTH_PASSWORD_HASH', ''),
                   cookie_secure=boolean('AUTH_COOKIE_SECURE', 'true'),
                   mode=values.get('AUTH_MODE', 'password').strip().lower(),
                   local_proxy=boolean('AUTH_LOCAL_PROXY', 'false'),
                   bind_address=values.get('BIND_ADDRESS', '127.0.0.1'))
