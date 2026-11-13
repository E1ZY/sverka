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


def test_training_documents_by_role_download_original_bytes_without_creating_case(client):
    manifest = json.loads((ROOT/'demo/manifest.json').read_text(encoding='utf-8'))
    before = client.get('/api/cases').json()
    for role, count in [('report', 1), ('primary', 22)]:
        response = client.get('/api/demo/documents', params={'role': role})
        assert response.status_code == 200
        documents = response.json()
        assert len(documents) == count
        assert {doc['name'] for doc in documents} == {item['name'] for item in manifest['files'] if item['role'] == role}
        assert client.get('/api/demo/documents', params={'role': role}).json() == documents
        for document in documents:
            assert isinstance(document['last_modified'], int)
            downloaded = client.get(document['url'])
            assert downloaded.status_code == 200
            assert downloaded.content == (DEMO_DIR/document['name']).read_bytes()
    assert client.get('/api/cases').json() == before


def test_training_document_lookup_cannot_select_unlisted_files(client):
    assert client.get('/api/demo/documents', params={'role': 'answers'}).status_code == 422
    assert client.get('/api/demo/documents/-1/original').status_code == 404
    assert client.get('/api/demo/documents/23/original').status_code == 404
    assert client.get('/api/demo/documents/expected.json/original').status_code == 422


def test_training_document_buttons_report_missing_kit(client, tmp_path, monkeypatch):
    monkeypatch.setattr('app.main.DEMO_DIR', tmp_path)
    assert client.get('/api/demo/documents', params={'role': 'report'}).status_code == 404
    assert client.get('/api/demo/documents', params={'role': 'primary'}).status_code == 404
    assert client.get('/api/demo/documents/0/original').status_code == 404
