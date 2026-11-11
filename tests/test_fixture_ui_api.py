import json
import shutil
from pathlib import Path
from unittest.mock import patch

from app.pipeline import claim, process

ROOT = Path(__file__).resolve().parent.parent


def test_catalog_contains_context_without_oracle_values(client):
    response = client.get('/api/fixtures')
    assert response.status_code == 200
    fixtures = response.json()
    assert len(fixtures) == 31
    assert fixtures[0]['id'] == 'original_task_data'
    assert fixtures[0]['origin'] == 'task'
    assert fixtures[0]['context']['contract'] == '24/03/15-01'
    assert fixtures[0]['input_files'] == 23
    synthetic = next(f for f in fixtures if f['id'] == '00_clean')
    assert synthetic['origin'] == 'generated'
    assert synthetic['context']['contract'] == '26/01/01-77'
    assert synthetic['input_files'] == 5
    assert 'metrics' not in response.text
    assert 'expected.json' not in response.text
    assert next(f for f in fixtures if f['id'] == '20_vat_components')['known_limitation']


def test_original_fixture_uses_only_source_documents_and_compares_after_calculation(client):
    manifest = json.loads((ROOT/'demo/manifest.json').read_text(encoding='utf-8'))
    with patch('app.fixtures.load_oracle', side_effect=AssertionError('Oracle read before calculation')):
        response = client.post('/api/fixtures/original_task_data/runs')
        assert response.status_code == 202, response.text
        queued = response.json()
        before = client.get('/api/cases/'+queued['case_id']).json()
        assert before['context']['fixture_id'] == 'original_task_data'
        assert before['context']['contract'] == manifest['context']['contract']
        assert before['result'] is None
        assert before['fixture_comparison'] is None
        assert len(before['documents']) == 23
        assert {d['name'] for d in before['documents']} == {f['name'] for f in manifest['files']}
        assert claim() == queued['run_id']
        process(queued['run_id'])
    after = client.get('/api/cases/'+queued['case_id']).json()
    assert after['status'] == 'completed'
    assert after['result']['metrics'][-1]['delta'] == '12500.00'
    assert after['result']['summary']['included_documents'] == 19
    assert after['fixture_comparison']['matches'] is True
    assert after['fixture_comparison']['differences'] == []


def test_launch_runs_real_documents_and_compares_only_after_completion(client):
    with patch('app.fixtures.load_oracle', side_effect=AssertionError('Oracle read before calculation')):
        response = client.post('/api/fixtures/00_clean/runs')
        assert response.status_code == 202, response.text
        queued = response.json()
        before = client.get('/api/cases/'+queued['case_id']).json()
        assert before['result'] is None
        assert before['fixture_comparison'] is None
        assert len(before['documents']) == 5
        assert all(d['name'] not in {'case.json', 'expected.json'} for d in before['documents'])
        assert claim() == queued['run_id']
        process(queued['run_id'])
    after = client.get('/api/cases/'+queued['case_id']).json()
    assert after['status'] == 'completed'
    assert after['result']['metrics'][-1]['expected'] == '180000.00'
    assert after['fixture_comparison']['matches'] is True
    assert after['fixture_comparison']['differences'] == []
    assert after['fixture_comparison']['run_id'] == queued['run_id']
    assert 'fixture_comparison' not in after['result']


def test_known_limitation_shows_actual_differences(client):
    queued = client.post('/api/fixtures/20_vat_components/runs').json()
    assert claim() == queued['run_id']
    process(queued['run_id'])
    result = client.get('/api/cases/'+queued['case_id']).json()
    comparison = result['fixture_comparison']
    assert comparison['available'] is True
    assert comparison['matches'] is False
    assert comparison['known_limitation']
    assert any(d['kind'] == 'status' and d['expected'] == 'MATCH' and d['actual'] == 'INSUFFICIENT_DATA'
               for d in comparison['differences'])


def test_corrupt_fixture_rejected_without_creating_case_or_job(client):
    before = client.get('/api/cases').json()
    response = client.post('/api/fixtures/28_corrupt_xlsx_upload/runs')
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'rejected'
    assert result['filename'] == 'broken.xlsx'
    assert result['matches_expected'] is True
    assert result['actual_http_status'] == result['expected_http_status'] == 400
    assert client.get('/api/cases').json() == before


def test_invalid_fixture_id_is_not_a_file_path(client):
    assert client.post('/api/fixtures/not_in_catalog/runs').status_code == 404
    # A decoded slash cannot match the fixture route. A built static frontend
    # rejects the fallback POST with 405; an API-only checkout returns 404.
    assert client.post('/api/fixtures/%2E%2E%2Fdata/runs').status_code in {404, 405}


def test_modified_fixture_is_rejected_before_import(client, tmp_path, monkeypatch):
    import app.fixtures as fixtures
    source = ROOT/'cases/generated/00_clean'
    folder = tmp_path/'generated/00_clean'
    folder.parent.mkdir()
    shutil.copytree(source, folder)
    (tmp_path/'catalog.json').write_text(json.dumps({'cases':[{'id':'00_clean'}]}), encoding='utf-8')
    with (folder/'input/primary/production.pdf').open('ab') as stream:
        stream.write(b'changed')
    monkeypatch.setattr(fixtures, 'FIXTURES_DIR', tmp_path)
    before = client.get('/api/cases').json()
    assert client.post('/api/fixtures/00_clean/runs').status_code == 409
    assert client.get('/api/cases').json() == before


def test_manual_check_has_no_fixture_comparison(client, baseline):
    response = client.get('/api/cases/'+baseline['id']).json()
    assert response['fixture_comparison'] is None


def test_missing_catalog_keeps_normal_application_available(client, tmp_path, monkeypatch):
    import app.fixtures as fixtures
    monkeypatch.setattr(fixtures, 'FIXTURES_DIR', tmp_path)
    assert [f['id'] for f in client.get('/api/fixtures').json()] == ['original_task_data']
    monkeypatch.setattr(fixtures, 'DEMO_DIR', tmp_path/'missing')
    assert client.get('/api/fixtures').json() == []
    assert client.get('/api/health').status_code == 200


def test_missing_original_documents_keeps_synthetic_catalog(client, tmp_path, monkeypatch):
    import app.fixtures as fixtures
    monkeypatch.setattr(fixtures, 'DEMO_DIR', tmp_path/'missing')
    catalog = client.get('/api/fixtures').json()
    assert len(catalog) == 30
    assert all(f['origin'] == 'generated' for f in catalog)
    before = client.get('/api/cases').json()
    assert client.post('/api/fixtures/original_task_data/runs').status_code == 404
    assert client.get('/api/cases').json() == before
