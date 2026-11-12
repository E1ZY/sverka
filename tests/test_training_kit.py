import io
import json
import zipfile

from app.config import DEMO_DIR, ROOT


def test_training_kit_contains_only_source_documents_without_creating_case(client):
    manifest = json.loads((ROOT/'demo/manifest.json').read_text(encoding='utf-8'))
    before = client.get('/api/cases').json()
    response = client.get('/api/demo/documents.zip')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {f"{item['role']}/{item['name']}" for item in manifest['files']}
        assert archive.testzip() is None
        for item in manifest['files']:
            assert archive.read(f"{item['role']}/{item['name']}") == (DEMO_DIR/item['name']).read_bytes()
    assert client.get('/api/cases').json() == before


def test_incomplete_training_kit_returns_clear_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr('app.main.DEMO_DIR', tmp_path)
    response = client.get('/api/demo/documents.zip')
    assert response.status_code == 404
    assert 'не установлены полностью' in response.json()['detail']
