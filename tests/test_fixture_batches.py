from unittest.mock import patch

import pytest
from fastapi import HTTPException

import app.main as main
from app.db import Case, Run, Session
from app.pipeline import claim, process


@pytest.fixture
def select_catalog(monkeypatch):
    catalog = {item['id']: item for item in main.list_fixtures()}

    def select(*ids):
        items = [dict(catalog[key]) for key in ids]
        monkeypatch.setattr(main, 'list_fixtures', lambda: items)
        return items

    return select


def test_batch_runs_all_selected_cases_and_restores_saved_results(client, select_catalog):
    select_catalog('original_task_data', '00_clean', '20_vat_components', '28_corrupt_xlsx_upload')
    with patch('app.fixtures.load_oracle', side_effect=AssertionError('Oracle read before calculation')):
        response = client.post('/api/fixture-batches')
        assert response.status_code == 202, response.text
        batch = response.json()
        assert batch['total'] == 4
        assert batch['done'] == 1
        assert batch['counts']['queued'] == 3
        assert batch['counts']['passed'] == 1
        before = client.get('/api/cases').json()
        assert client.post('/api/fixture-batches').status_code == 409
        assert client.get('/api/cases').json() == before
        for item in batch['items']:
            if item['run_id']:
                assert claim() == item['run_id']
                process(item['run_id'])
    result = client.get('/api/fixture-batches/'+batch['id']).json()
    assert result['status'] == 'completed'
    assert result['done'] == result['total'] == 4
    assert result['progress'] == 100
    assert result['counts']['passed'] == 3
    assert result['counts']['known_limitations'] == 1
    assert result['counts']['failed'] == result['counts']['errors'] == 0
    assert result['items'][2]['differences'] > 0
    assert result['items'][3]['case_id'] is None
    assert 'HTTP 400' in result['items'][3]['message']
    assert client.get('/api/fixture-batches/latest').json() == result

    # A later manual rerun does not change which jobs the batch observes.
    first = result['items'][0]
    rerun = client.post('/api/cases/'+first['case_id']+'/runs').json()
    unchanged = client.get('/api/fixture-batches/'+batch['id']).json()
    assert unchanged == result
    assert claim() == rerun['id']
    process(rerun['id'])

    # A finished batch releases its slot for the next click.
    select_catalog('28_corrupt_xlsx_upload')
    next_batch = client.post('/api/fixture-batches')
    assert next_batch.status_code == 202
    assert next_batch.json()['id'] != batch['id']
    assert next_batch.json()['status'] == 'completed'


def test_bad_fixture_does_not_block_other_cases(client, select_catalog, monkeypatch):
    select_catalog('00_clean', '28_corrupt_xlsx_upload')
    original = main.fixture_inputs

    def changed(fixture_id):
        if fixture_id == '00_clean':
            raise HTTPException(409, 'Входные файлы изменились')
        return original(fixture_id)

    monkeypatch.setattr(main, 'fixture_inputs', changed)
    before = client.get('/api/cases').json()
    response = client.post('/api/fixture-batches')
    assert response.status_code == 202, response.text
    batch = response.json()
    assert batch['status'] == 'completed'
    assert batch['counts']['errors'] == batch['counts']['passed'] == 1
    assert batch['items'][0]['message'] == 'Входные файлы изменились'
    assert client.get('/api/cases').json() == before


def test_worker_failure_is_a_new_error_and_other_jobs_continue(client, select_catalog):
    select_catalog('00_clean', '01_overstatement')
    batch = client.post('/api/fixture-batches').json()
    first, second = batch['items']
    assert claim() == first['run_id']
    with Session.begin() as session:
        run = session.get(Run, first['run_id'])
        run.status, run.message = 'failed', 'OCR недоступен'
        session.get(Case, first['case_id']).status = 'failed'
    assert claim() == second['run_id']
    process(second['run_id'])
    result = client.get('/api/fixture-batches/'+batch['id']).json()
    assert result['status'] == 'completed'
    assert result['counts']['errors'] == result['counts']['passed'] == 1
    assert result['counts']['known_limitations'] == 0
    assert result['items'][0]['message'] == 'OCR недоступен'


def test_missing_oracle_is_not_a_pass_and_fixed_limitation_is_distinct(client, select_catalog):
    items = select_catalog('00_clean', '01_overstatement')
    items[0]['known_limitation'] = 'Ранее известная ошибка'
    batch = client.post('/api/fixture-batches').json()
    for item in batch['items']:
        assert claim() == item['run_id']
        process(item['run_id'])
    import app.fixtures as fixtures
    original = fixtures.load_oracle

    def missing(fixture_id):
        if fixture_id == '01_overstatement':
            raise FileNotFoundError('Нет эталона')
        return original(fixture_id)

    with patch('app.fixtures.load_oracle', side_effect=missing):
        result = client.get('/api/fixture-batches/'+batch['id']).json()
    assert result['status'] == 'completed'
    assert result['counts']['unexpected_passes'] == result['counts']['errors'] == 1
    assert result['counts']['passed'] == 0
    assert result['items'][0]['status'] == 'unexpected_pass'
    assert result['items'][1]['status'] == 'error'


def test_empty_catalog_and_unknown_batch(client, select_catalog):
    select_catalog()
    assert client.post('/api/fixture-batches').status_code == 400
    assert client.get('/api/fixture-batches/does-not-exist').status_code == 404
