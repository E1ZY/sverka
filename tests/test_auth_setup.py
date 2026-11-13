import pytest

from app.auth import AuthSettings
from app.auth_passwords import password_hash, verify_password
from scripts.configure_auth import save_settings


def test_password_hash_has_random_salt_and_supports_unicode():
    password = 'Длинный пароль для проверки'
    first, second = password_hash(password), password_hash(password)
    assert first != second
    assert password not in first
    assert verify_password(password, first)
    assert not verify_password('неверный пароль', first)
    with pytest.raises(ValueError):
        password_hash('short')
    with pytest.raises(ValueError):
        AuthSettings('invalid')


def test_setup_preserves_database_password_and_other_settings(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# Local configuration\nPOSTGRES_PASSWORD=keep-existing-value\nDATA_DIR=/data\n'
                    'AUTH_PASSWORD_HASH=old\nAUTH_COOKIE_SECURE=false\n', encoding='utf-8')
    encoded = password_hash('new-workspace-password')
    save_settings(path, encoded, True)
    result = path.read_text(encoding='utf-8')
    assert '# Local configuration\nPOSTGRES_PASSWORD=keep-existing-value\nDATA_DIR=/data\n' in result
    assert result.count('AUTH_PASSWORD_HASH=') == 1
    assert f'AUTH_PASSWORD_HASH={encoded}\n' in result
    assert 'AUTH_COOKIE_SECURE=true\n' in result
    assert 'new-workspace-password' not in result
