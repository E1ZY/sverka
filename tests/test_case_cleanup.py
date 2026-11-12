from unittest.mock import patch
import shutil

import pytest
from sqlalchemy import delete, select

from app.config import DATA
from app.db import Case, Document, FixtureBatch, Review, Run, Session


created_cases = []
created_batches = []


@pytest.fixture(autouse=True)
def cleanup_test_records():
    created_cases.clear()
    created_batches.clear()
    yield
    with Session.begin() as session:
        session.execute(delete(FixtureBatch).where(FixtureBatch.id.in_(created_batches)))
        for model in (Review, Run, Document):
            session.execute(delete(model).where(model.case_id.in_(created_cases)))
        session.execute(delete(Case).where(Case.id.in_(created_cases)))
    for case_id in created_cases:
        directory = DATA/case_id
        assert directory.resolve().parent == DATA.resolve()
        if directory.exists():
            shutil.rmtree(directory)


def make_case(client, title='Для удаления', status='completed'):
    case = client.post('/api/cases', json={
        'title': title, 'contract': 'cleanup-test', 'stage': 1,
        'period_start': '2026-01-01', 'period_end': '2026-01-31',
    }).json()
    created_cases.append(case['id'])
    directory = DATA/case['id']
    directory.mkdir()
    path = directory/'uploaded.pdf'
    path.write_bytes(b'local test copy')
    with Session.begin() as session:
        stored = session.get(Case, case['id'])
        stored.status = status
        document = Document(case_id=case['id'], name='uploaded.pdf', path=str(path), sha256='a'*64, role='primary')
        run = Run(case_id=case['id'], status=status, payload={'saved': True})
        session.add_all([document, run])
        session.flush()
        session.add(Review(case_id=case['id'], document_id=document.id, changes={'amount': '100'}, before={}, reason='Test review'))
        stored.active_run_id = run.id
    return case['id'], directory


def remove(client, ids):
    return client.request('DELETE', '/api/cases', json={'case_ids': ids})


def test_clear_removes_only_confirmed_cases_with_files_results_and_reviews(client):
    first, first_dir = make_case(client)
    second, second_dir = make_case(client)
    keep, keep_dir = make_case(client, 'Оставить')
    response = remove(client, [first, second])
    assert response.status_code == 200, response.text
    assert set(response.json()['deleted_ids']) == {first, second}
    assert response.json()['cleanup_failed'] == []
    assert not first_dir.exists() and not second_dir.exists()
    assert (keep_dir/'uploaded.pdf').read_bytes() == b'local test copy'
    for case_id in (first, second):
        assert client.get('/api/cases/'+case_id).status_code == 404
        with Session() as session:
            for model in (Document, Run, Review):
                assert session.scalar(select(model.id).where(model.case_id == case_id)) is None
    assert client.get('/api/cases/'+keep).status_code == 200
    assert not {first, second} & {case['id'] for case in client.get('/api/cases').json()}
    assert remove(client, [first, first, second]).json() == {'deleted_ids': [], 'cleanup_failed': []}


@pytest.mark.parametrize('active_status', ['queued', 'running'])
def test_active_case_blocks_entire_request_without_partial_deletion(client, active_status):
    finished, finished_dir = make_case(client)
    active, active_dir = make_case(client, status=active_status)
    response = remove(client, [finished, active])
    assert response.status_code == 409
    assert finished_dir.exists() and active_dir.exists()
    assert client.get('/api/cases/'+finished).status_code == 200
    assert client.get('/api/cases/'+active).status_code == 200


def test_running_job_is_protected_even_if_case_status_is_stale(client):
    case_id, directory = make_case(client)
    with Session.begin() as session:
        session.scalar(select(Run).where(Run.case_id == case_id)).status = 'running'
    assert remove(client, [case_id]).status_code == 409
    assert directory.exists()


def test_active_catalog_batch_keeps_its_completed_case(client):
    finished, directory = make_case(client)
    active, _ = make_case(client, status='running')
    with Session.begin() as session:
        runs = {run.case_id: run.id for run in session.scalars(select(Run).where(Run.case_id.in_([finished, active])))}
        batch = FixtureBatch(active_key='cleanup-test-batch', items=[
            {'fixture_id': '00_clean', 'case_id': case_id, 'run_id': runs[case_id],
             'status': 'queued', 'title': 'Test', 'known_limitation': None}
            for case_id in (finished, active)
        ])
        session.add(batch)
        session.flush()
        created_batches.append(batch.id)
    assert remove(client, [finished]).status_code == 409
    assert directory.exists()


def test_file_cleanup_failure_is_reported_after_database_deletion(client):
    case_id, directory = make_case(client)
    with patch('app.main.shutil.rmtree', side_effect=PermissionError('File is locked')):
        response = remove(client, [case_id])
    assert response.status_code == 200
    assert response.json() == {'deleted_ids': [case_id], 'cleanup_failed': [case_id]}
    assert client.get('/api/cases/'+case_id).status_code == 404
    assert directory.exists()


def test_clear_validates_ids_before_touching_files(client):
    case_id, directory = make_case(client)
    for ids in ([], ['../'], [case_id]*101):
        assert remove(client, ids).status_code == 422
    assert directory.exists()
