import hashlib
import os
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth
from app.auth_passwords import password_hash
from app.db import AuthSession, now
from app.main import app

PASSWORD = 'test-workspace-password'
LOGIN_HEADERS = {'X-Sverka-Request': '1'}


@pytest.fixture
def workspace(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    AuthSession.__table__.create(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth, 'Session', sessions)
    application = FastAPI()
    auth.install_auth(application, auth.AuthSettings(os.environ['AUTH_PASSWORD_HASH'], False))

    @application.get('/api/private')
    def read():
        return {'private': True}

    @application.post('/api/private')
    def write():
        return {'saved': True}

    with TestClient(application) as browser:
        yield browser, application.state.auth, sessions
    engine.dispose()


def login(browser, password=PASSWORD):
    return browser.post('/api/auth/login', json={'password': password}, headers=LOGIN_HEADERS)


@pytest.mark.parametrize('method,path', [
    ('GET', '/api/cases'), ('POST', '/api/cases'), ('DELETE', '/api/cases'),
    ('GET', '/api/cases/example'), ('POST', '/api/cases/example/documents'),
    ('POST', '/api/cases/example/runs'), ('POST', '/api/cases/example/documents/doc/review'),
    ('GET', '/api/cases/example/documents/doc/original'),
    ('GET', '/api/cases/example/documents/doc/page/1'), ('GET', '/api/cases/example/runs/run/export'),
    ('POST', '/api/reports/context'), ('POST', '/api/demo'), ('GET', '/api/demo/documents.zip'),
    ('GET', '/api/demo/documents'), ('GET', '/api/demo/documents/0/original'),
    ('GET', '/api/fixtures'), ('POST', '/api/fixtures/example/runs'),
    ('POST', '/api/fixture-batches'), ('GET', '/api/fixture-batches/latest'),
    ('GET', '/docs'), ('GET', '/redoc'), ('GET', '/openapi.json'),
])
def test_actual_application_denies_anonymous_access(client, method, path):
    # The application's real middleware must reject before routing or parsing
    # a body; protecting only the React screen would not pass this test.
    with TestClient(app) as anonymous:
        response = anonymous.request(method, path)
    assert response.status_code == 401, response.text
    assert response.headers['cache-control'] == 'no-store'


def test_unconfigured_installation_keeps_data_closed(workspace):
    application = FastAPI()
    auth.install_auth(application, auth.AuthSettings())
    with TestClient(application) as browser:
        assert browser.get('/api/auth/session').json() == {
            'configured': False, 'authenticated': False, 'csrf_token': None, 'mode': 'password'}
        assert browser.get('/api/private').status_code == 503
        assert login(browser).status_code == 503


def test_login_stores_only_token_hash_and_returns_private_session(workspace):
    browser, service, sessions = workspace
    assert browser.get('/api/auth/session').json()['csrf_token'] is None
    assert login(browser, 'wrong').status_code == 401
    assert not browser.cookies
    response = login(browser)
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Max-Age=43200' in cookie
    token = browser.cookies.get(auth.COOKIE_NAME)
    assert token not in response.text
    with sessions() as session:
        record = session.scalar(select(AuthSession))
        assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert record.csrf_token == response.json()['csrf_token']
    assert browser.get('/api/private').status_code == 200
    assert browser.get('/api/auth/session').json()['csrf_token'] == response.json()['csrf_token']
    # A new service object (process restart) recognizes the database session.
    assert auth.AuthService(service.settings).authenticate(token) is not None


def test_csrf_is_required_for_writes_and_logout(workspace):
    browser, _, _ = workspace
    csrf = login(browser).json()['csrf_token']
    for path in ['/api/private', '/api/auth/logout']:
        assert browser.post(path).status_code == 403
        assert browser.post(path, headers={'X-CSRF-Token': 'forged'}).status_code == 403
    assert browser.post('/api/private', headers={'X-CSRF-Token': csrf}).status_code == 200


def test_logout_revokes_copied_cookie_and_clears_browser(workspace):
    browser, _, _ = workspace
    csrf = login(browser).json()['csrf_token']
    token = browser.cookies.get(auth.COOKIE_NAME)
    response = browser.post('/api/auth/logout', headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert browser.get('/api/private').status_code == 401
    replay = browser.get('/api/private', headers={'Cookie': f'{auth.COOKIE_NAME}={token}'})
    assert replay.status_code == 401


def test_expired_tampered_and_rotated_password_sessions_are_denied(workspace):
    browser, service, sessions = workspace
    login(browser)
    token = browser.cookies.get(auth.COOKIE_NAME)
    assert service.authenticate(token[:-1] + ('a' if token[-1] != 'a' else 'b')) is None
    rotated = auth.AuthService(auth.AuthSettings(password_hash('another-test-password'), False))
    assert rotated.authenticate(token) is None
    with sessions.begin() as session:
        record = session.scalar(select(AuthSession))
        record.expires_at = now() - timedelta(seconds=1)
    assert browser.get('/api/private').status_code == 401


def test_new_login_rotates_and_revokes_old_session(workspace):
    browser, service, _ = workspace
    first = login(browser)
    token = browser.cookies.get(auth.COOKIE_NAME)
    second = login(browser)
    assert browser.cookies.get(auth.COOKIE_NAME) != token
    assert second.json()['csrf_token'] != first.json()['csrf_token']
    assert service.authenticate(token) is None


def test_login_limits_attempts_even_with_forged_forwarded_headers(workspace):
    browser, service, _ = workspace
    clock = [1000.0]
    service.limiter.clock = lambda: clock[0]
    for attempt in range(5):
        response = browser.post('/api/auth/login', json={'password': 'wrong'},
                                headers={**LOGIN_HEADERS, 'X-Forwarded-For': f'192.0.2.{attempt}'})
        assert response.status_code == 401
    blocked = login(browser)
    assert blocked.status_code == 429
    assert blocked.headers['retry-after'] == '300'
    clock[0] += 301
    assert login(browser).status_code == 200


@pytest.mark.parametrize('body', [b'{}', b'[]', b'{"password":123}', b'not-json',
                                 b'{"password":"' + b'a' * 1025 + b'"}'])
def test_invalid_login_does_not_echo_password_or_internal_errors(workspace, body):
    browser, _, _ = workspace
    response = browser.post('/api/auth/login', content=body,
                            headers={**LOGIN_HEADERS, 'Content-Type': 'application/json'})
    assert response.status_code == 400
    assert response.json() == {'detail': 'Укажите пароль.'}


def test_cross_origin_form_login_and_oversized_body_are_rejected(workspace):
    browser, _, _ = workspace
    assert browser.post('/api/auth/login', json={'password': PASSWORD}).status_code == 403
    assert browser.post('/api/auth/login', data={'password': PASSWORD}, headers=LOGIN_HEADERS).status_code == 403
    oversized = browser.post('/api/auth/login', content=b'a' * 4097,
                             headers={**LOGIN_HEADERS, 'Content-Type': 'application/json'})
    assert oversized.status_code == 413
    invalid_unicode = browser.post('/api/auth/login', content=b'{"password":"\\ud800"}',
                                   headers={**LOGIN_HEADERS, 'Content-Type': 'application/json'})
    assert invalid_unicode.status_code == 401


def test_https_mode_sets_secure_cookie(workspace):
    application = FastAPI()
    auth.install_auth(application, auth.AuthSettings(os.environ['AUTH_PASSWORD_HASH'], True))
    with TestClient(application, base_url='https://testserver') as browser:
        response = login(browser)
        assert '; Secure' in response.headers['set-cookie']
        assert browser.get('/api/auth/session').json()['authenticated'] is True


def test_global_login_limit_and_client_cache_are_bounded():
    limiter = auth.LoginLimiter()
    limiter.clock = lambda: 1000.0
    assert all(limiter.attempt(f'client-{i}') == 0 for i in range(60))
    assert limiter.attempt('one-more') == 60
    for i in range(3000):
        limiter.attempt(f'new-client-{i}')
    assert len(limiter.clients) == 2048
    assert len(limiter.total) == 60
