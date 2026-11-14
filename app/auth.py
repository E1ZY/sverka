"""Shared workspace login. Sessions are opaque, revocable and stored as hashes."""
import hashlib
import hmac
import ipaddress
import json
import math
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from datetime import timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from .auth_config import AuthSettings, is_loopback
from .auth_passwords import verify_password
from .db import AuthSession, Session, now

SESSION_SECONDS = 12 * 60 * 60
COOKIE_NAME = 'sverka_session'
TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z')
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
PUBLIC_PATHS = {'/', '/index.html', '/api/health', '/api/auth/session', '/api/auth/login'}


class LoginLimiter:
    """Bounded per-process limits for the single API process used by Compose."""
    def __init__(self):
        self.clock = time.monotonic
        self.lock = threading.Lock()
        self.clients = OrderedDict()
        self.total = deque()

    def attempt(self, client):
        with self.lock:
            current = self.clock()
            attempts = self.clients.pop(client, deque())
            while attempts and attempts[0] <= current - 300:
                attempts.popleft()
            while self.total and self.total[0] <= current - 60:
                self.total.popleft()
            self.clients[client] = attempts
            if len(self.clients) > 2048:
                self.clients.popitem(last=False)
            if len(attempts) >= 5:
                return max(1, math.ceil(attempts[0] + 300 - current))
            if len(self.total) >= 60:
                return max(1, math.ceil(self.total[0] + 60 - current))
            attempts.append(current)
            self.total.append(current)
            return 0

    def success(self, client):
        with self.lock:
            self.clients.pop(client, None)


class AuthService:
    def __init__(self, settings):
        self.settings = settings
        self.credential_tag = hashlib.sha256(settings.password_hash.encode()).hexdigest()
        self.limiter = LoginLimiter()

    def authenticate(self, token):
        if self.settings.mode == 'local' or not self.settings.password_hash or not token or not TOKEN.fullmatch(token):
            return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with Session() as session:
            record = session.get(AuthSession, token_hash)
            if record is None or record.credential_tag != self.credential_tag:
                return None
            expires = record.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now():
                return None
            return record

    def create_session(self, previous_token):
        token = secrets.token_urlsafe(32)
        record = AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                             csrf_token=secrets.token_urlsafe(32), credential_tag=self.credential_tag,
                             expires_at=now() + timedelta(seconds=SESSION_SECONDS))
        with Session.begin() as session:
            session.execute(delete(AuthSession).where(AuthSession.expires_at <= now()))
            session.execute(delete(AuthSession).where(AuthSession.credential_tag != self.credential_tag))
            if previous_token:
                session.execute(delete(AuthSession).where(
                    AuthSession.token_hash == hashlib.sha256(previous_token.encode()).hexdigest()))
            session.add(record)
        return token, record


class AuthMiddleware:
    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        path = scope['path']
        public = path in PUBLIC_PATHS or path.startswith('/assets/')
        if scope['type'] == 'websocket':
            # No WebSocket API exists; do not accidentally expose future routes.
            return await send({'type': 'websocket.close', 'code': 1008})
        request = Request(scope)

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                if not path.startswith('/assets/'):
                    headers = [(k, v) for k, v in headers if k.lower() != b'cache-control']
                    headers.append((b'cache-control', b'no-store'))
                headers.extend([(b'x-content-type-options', b'nosniff'),
                                (b'x-frame-options', b'DENY'), (b'referrer-policy', b'same-origin')])
                message = {**message, 'headers': headers}
            await send(message)

        if self.service.settings.mode == 'local' and path != '/api/health':
            # Host checks prevent DNS rebinding; peer checks also prevent direct
            # access after an accidental --host 0.0.0.0. Docker explicitly opts
            # into bridge peers while publishing its port on loopback only.
            peer = request.client.host if request.client else ''
            allowed_peer = is_loopback(peer)
            if not allowed_peer and self.service.settings.local_proxy:
                try:
                    allowed_peer = ipaddress.ip_address(peer).is_private
                except ValueError:
                    pass
            if not is_loopback(request.url.hostname or '') or not allowed_peer:
                return await JSONResponse({'detail': 'Локальный режим доступен только через localhost.'}, status_code=403)(scope, receive, protected_send)
            if scope['method'] not in SAFE_METHODS:
                origin = request.headers.get('origin')
                expected_origin = f'{request.url.scheme}://{request.url.netloc}'
                if request.headers.get('x-sverka-request') != '1' or (origin and origin != expected_origin):
                    return await JSONResponse({'detail': 'Откройте приложение на localhost и повторите действие.'}, status_code=403)(scope, receive, protected_send)
        elif not public:
            if not self.service.settings.password_hash:
                return await JSONResponse({'detail': 'Вход в приложение ещё не настроен.'}, status_code=503)(scope, receive, protected_send)
            identity = await run_in_threadpool(self.service.authenticate, request.cookies.get(COOKIE_NAME))
            if identity is None:
                return await JSONResponse({'detail': 'Войдите в приложение.'}, status_code=401)(scope, receive, protected_send)
            if scope['method'] not in SAFE_METHODS:
                csrf = Headers(scope=scope).get('x-csrf-token', '')
                if not hmac.compare_digest(csrf.encode(), identity.csrf_token.encode()):
                    return await JSONResponse({'detail': 'Обновите страницу и повторите действие.'}, status_code=403)(scope, receive, protected_send)
            scope.setdefault('state', {})['auth_session'] = identity
        return await self.app(scope, receive, protected_send)


def install_auth(app: FastAPI, settings=None):
    service = AuthService(settings or AuthSettings.from_env())
    app.state.auth = service
    app.add_middleware(AuthMiddleware, service=service)

    @app.get('/api/auth/session')
    def auth_session(request: Request):
        if service.settings.mode == 'local':
            return {'configured': True, 'authenticated': True, 'csrf_token': None, 'mode': 'local'}
        identity = service.authenticate(request.cookies.get(COOKIE_NAME))
        return {'configured': bool(service.settings.password_hash), 'authenticated': identity is not None,
                'csrf_token': identity.csrf_token if identity else None, 'mode': 'password'}

    @app.post('/api/auth/login')
    async def login(request: Request):
        if service.settings.mode == 'local':
            return {'authenticated': True, 'csrf_token': None, 'mode': 'local'}
        if not service.settings.password_hash:
            return JSONResponse({'detail': 'Вход в приложение ещё не настроен.'}, status_code=503)
        # Custom header + JSON prevents cross-origin forms from logging a user
        # into the shared account. No cross-origin CORS access is granted.
        if request.headers.get('x-sverka-request') != '1' or request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
            return JSONResponse({'detail': 'Откройте страницу входа и повторите попытку.'}, status_code=403)
        client = request.client.host if request.client else 'unknown'
        retry = service.limiter.attempt(client)
        if retry:
            return JSONResponse({'detail': 'Слишком много попыток входа. Попробуйте позже.'}, status_code=429,
                                headers={'Retry-After': str(retry)})
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                return JSONResponse({'detail': 'Слишком длинный запрос.'}, status_code=413)
        try:
            body = json.loads(raw)
            password = body.get('password') if isinstance(body, dict) else None
        except (ValueError, UnicodeDecodeError):
            password = None
        if not isinstance(password, str) or not 1 <= len(password) <= 1024:
            return JSONResponse({'detail': 'Укажите пароль.'}, status_code=400)
        if not await run_in_threadpool(verify_password, password, service.settings.password_hash):
            return JSONResponse({'detail': 'Неверный пароль.'}, status_code=401)
        token, identity = await run_in_threadpool(service.create_session, request.cookies.get(COOKIE_NAME))
        service.limiter.success(client)
        response = JSONResponse({'authenticated': True, 'csrf_token': identity.csrf_token})
        response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, path='/', httponly=True,
                            secure=service.settings.cookie_secure, samesite='strict')
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request):
        if service.settings.mode == 'password':
            with Session.begin() as session:
                session.execute(delete(AuthSession).where(AuthSession.token_hash == request.state.auth_session.token_hash))
        response = JSONResponse({'authenticated': service.settings.mode == 'local'})
        response.delete_cookie(COOKIE_NAME, path='/', secure=service.settings.cookie_secure, httponly=True, samesite='strict')
        return response
