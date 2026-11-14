"""Local access is explicit and stays restricted to the local computer."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthSettings, install_auth


def application(**settings):
    app = FastAPI()
    install_auth(app, AuthSettings(mode='local', **settings))

    @app.get('/api/private')
    def read():
        return {'private': True}

    @app.post('/api/private')
    def write():
        return {'saved': True}

    return app


@pytest.mark.parametrize('host,peer', [('127.0.0.1', '127.0.0.1'), ('localhost', '::1'), ('[::1]', '::ffff:127.0.0.1')])
def test_local_workspace_opens_without_password_or_session(host, peer):
    with TestClient(application(), base_url=f'http://{host}:8000', client=(peer, 50000)) as browser:
        session = browser.get('/api/auth/session')
        assert session.json() == {'configured': True, 'authenticated': True, 'csrf_token': None, 'mode': 'local'}
        assert not browser.cookies
        assert browser.get('/api/private').json() == {'private': True}
        assert browser.get('/api/private').headers['cache-control'] == 'no-store'
        assert browser.post('/api/private', headers={'X-Sverka-Request': '1'}).json() == {'saved': True}
        assert browser.post('/api/auth/logout', headers={'X-Sverka-Request': '1'}).json()['authenticated'] is True
        assert browser.get('/api/private').status_code == 200


@pytest.mark.parametrize('host,peer', [('evil.example', '127.0.0.1'), ('127.0.0.1', '192.168.1.5'), ('127.0.0.1', '8.8.8.8')])
def test_local_workspace_rejects_remote_hosts_and_peers(host, peer):
    with TestClient(application(), base_url=f'http://{host}:8000', client=(peer, 50000)) as browser:
        for path in ['/api/private', '/api/auth/session', '/']:
            assert browser.get(path).status_code == 403


def test_local_writes_reject_cross_site_forms_and_foreign_origin():
    with TestClient(application(), base_url='http://localhost:8000', client=('127.0.0.1', 50000)) as browser:
        assert browser.post('/api/private').status_code == 403
        headers = {'X-Sverka-Request': '1', 'Origin': 'https://evil.example'}
        assert browser.post('/api/private', headers=headers).status_code == 403
        headers['Origin'] = 'http://localhost:8000'
        assert browser.post('/api/private', headers=headers).status_code == 200


def test_docker_bridge_requires_explicit_proxy_and_local_host():
    with TestClient(application(local_proxy=True), base_url='http://127.0.0.1:8000', client=('172.18.0.1', 50000)) as browser:
        assert browser.get('/api/private').status_code == 200
        assert browser.get('/api/private', headers={'Host': 'public.example'}).status_code == 403
    with TestClient(application(local_proxy=True), base_url='http://127.0.0.1:8000', client=('8.8.8.8', 50000)) as browser:
        assert browser.get('/api/private').status_code == 403


@pytest.mark.parametrize('binding', ['0.0.0.0', '::', '192.168.1.5'])
def test_local_mode_refuses_external_published_port(binding):
    with pytest.raises(ValueError, match='BIND_ADDRESS'):
        AuthSettings(mode='local', bind_address=binding)
