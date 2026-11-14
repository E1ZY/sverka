import pytest

from app.auth import AuthSettings
from app.auth_passwords import password_hash, verify_password
from scripts.configure_auth import save_settings
from scripts import configure_auth
from app.auth_config import KEYS


@pytest.fixture
def clean_auth_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


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
    assert 'AUTH_MODE=password\n' in result


def test_local_setup_clears_password_and_restores_local_binding(tmp_path, clean_auth_env):
    path = tmp_path / '.env'
    path.write_text('POSTGRES_PASSWORD=keep\nAUTH_MODE=password\nAUTH_PASSWORD_HASH=old\nBIND_ADDRESS=0.0.0.0\n', encoding='utf-8-sig')
    configure_auth.main(['--mode', 'local', '--env-file', str(path)])
    settings = AuthSettings.from_env(path)
    assert settings.mode == 'local' and not settings.password_hash
    assert not settings.cookie_secure and settings.bind_address == '127.0.0.1'
    assert 'POSTGRES_PASSWORD=keep\n' in path.read_text(encoding='utf-8')


def test_environment_overrides_file_and_missing_mode_defaults_to_password(tmp_path, clean_auth_env, monkeypatch):
    path = tmp_path / '.env'
    assert AuthSettings.from_env(path).mode == 'password'
    path.write_text('AUTH_MODE=local\n', encoding='utf-8')
    assert AuthSettings.from_env(path).mode == 'local'
    monkeypatch.setenv('AUTH_MODE', 'password')
    assert AuthSettings.from_env(path).mode == 'password'
    monkeypatch.setenv('AUTH_MODE', 'invalid')
    with pytest.raises(ValueError, match='AUTH_MODE'):
        AuthSettings.from_env(path)


@pytest.mark.parametrize('mode', ['local', 'password'])
def test_ensure_preserves_existing_configuration(tmp_path, clean_auth_env, mode):
    path = tmp_path / '.env'
    save_settings(path, password_hash('configured-workspace') if mode == 'password' else '', False, mode)
    before = path.read_bytes()
    configure_auth.main(['--ensure', '--http', '--env-file', str(path)])
    assert path.read_bytes() == before


def test_first_installation_can_choose_local_mode(tmp_path, clean_auth_env, monkeypatch):
    path = tmp_path / '.env'
    monkeypatch.setattr('sys.stdin.isatty', lambda: True)
    monkeypatch.setattr('builtins.input', lambda _: '1')
    configure_auth.main(['--ensure', '--http', '--env-file', str(path)])
    assert AuthSettings.from_env(path).mode == 'local'


def test_password_mode_stores_only_hash(tmp_path, clean_auth_env, monkeypatch):
    path = tmp_path / '.env'
    monkeypatch.setattr(configure_auth.getpass, 'getpass', lambda _: 'chosen-workspace-password')
    configure_auth.main(['--mode', 'password', '--http', '--env-file', str(path)])
    settings = AuthSettings.from_env(path)
    assert settings.mode == 'password' and not settings.cookie_secure
    assert verify_password('chosen-workspace-password', settings.password_hash)
    assert 'chosen-workspace-password' not in path.read_text(encoding='utf-8')


def test_missing_choice_fails_noninteractively_without_opening_access(tmp_path, clean_auth_env, monkeypatch, capsys):
    path = tmp_path / '.env'
    monkeypatch.setattr('sys.stdin.isatty', lambda: False)
    with pytest.raises(SystemExit) as error:
        configure_auth.main(['--ensure', '--env-file', str(path)])
    assert error.value.code == 2
    assert '--mode local' in capsys.readouterr().err
    assert not path.exists()
