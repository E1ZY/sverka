"""Password hashing shared with the dependency-free setup command."""
import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError('Пароль должен содержать от 12 до 1024 символов.')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256:{ITERATIONS}:{salt.hex()}:{digest.hex()}'


def parse_hash(encoded: str):
    try:
        algorithm, rounds, salt, digest = encoded.split(':')
        rounds = int(rounds)
        salt, digest = bytes.fromhex(salt), bytes.fromhex(digest)
        if algorithm != 'pbkdf2_sha256' or not ITERATIONS <= rounds <= 2_000_000 or len(salt) != 16 or len(digest) != 32:
            raise ValueError
        return rounds, salt, digest
    except (ValueError, TypeError):
        raise ValueError('Некорректный AUTH_PASSWORD_HASH. Запустите scripts/configure_auth.py.') from None


def verify_password(password: str, encoded: str) -> bool:
    rounds, salt, expected = parse_hash(encoded)
    try:
        raw = password.encode('utf-8')
    except UnicodeEncodeError:
        return False
    actual = hashlib.pbkdf2_hmac('sha256', raw, salt, rounds)
    return hmac.compare_digest(actual, expected)
