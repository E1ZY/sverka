import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
(ROOT/'.runtime').mkdir(exist_ok=True)
temp = Path(tempfile.mkdtemp(prefix='audit-tests-', dir=ROOT/'.runtime'))
os.environ['DATA_DIR'] = str(temp)
os.environ['DATABASE_URL'] = f'sqlite:///{(temp/"test.db").as_posix()}'
os.environ['EMBED_WORKER'] = 'false'
os.environ['OCR_PROVIDER'] = 'tesseract'
from app.auth_passwords import password_hash
TEST_PASSWORD = 'test-workspace-password'
os.environ['AUTH_PASSWORD_HASH'] = password_hash(TEST_PASSWORD)
os.environ['AUTH_COOKIE_SECURE'] = 'false'
os.environ['AUTH_MODE'] = 'password'

from fastapi.testclient import TestClient
from app.main import app
from app.pipeline import claim, process


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as c:
        response = c.post('/api/auth/login', json={'password': TEST_PASSWORD}, headers={'X-Sverka-Request': '1'})
        assert response.status_code == 200, response.text
        c.headers['X-CSRF-Token'] = response.json()['csrf_token']
        yield c


@pytest.fixture(scope='session')
def baseline(client):
    response = client.post('/api/demo')
    assert response.status_code == 201, response.text
    identifiers = response.json()
    run_id = claim()
    assert run_id == identifiers['run_id']
    process(run_id)
    case = client.get('/api/cases/'+identifiers['case_id']).json()
    assert case['status'] == 'completed', case
    return case
