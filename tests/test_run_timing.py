from copy import deepcopy
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, select

from app import db, pipeline, timing
from app.db import Case, Document, Run, Session


def cached_demo(client, baseline):
    demo = client.post('/api/demo').json()
    facts = {doc['name']: doc['extraction'] for doc in baseline['result']['documents']}
    with Session.begin() as session:
        for doc in session.scalars(select(Document).where(Document.case_id == demo['case_id'])):
            doc.extraction = deepcopy(facts[doc.name])
    return demo


def test_duration_excludes_queue_updates_live_and_freezes_on_completion(client, baseline, monkeypatch):
    demo = cached_demo(client, baseline)
    clock = [datetime(2026, 11, 14, 10, tzinfo=timezone.utc)]
    monkeypatch.setattr(pipeline, 'now', lambda: clock[0])
    monkeypatch.setattr(timing, 'now', lambda: clock[0])
    with Session.begin() as session:
        session.get(Run, demo['run_id']).created_at = clock[0] - timedelta(minutes=15)
    queued = client.get('/api/cases/' + demo['case_id']).json()
    assert queued['duration_seconds'] is None and queued['started_at'] is None
    assert pipeline.claim() == demo['run_id']
    clock[0] += timedelta(seconds=10)
    live = client.get('/api/cases/' + demo['case_id']).json()
    assert live['duration_seconds'] == live['runs'][0]['duration_seconds'] == 10
    assert live['finished_at'] is None
    clock[0] += timedelta(seconds=55.5)
    pipeline.process(demo['run_id'])
    clock[0] += timedelta(days=1)
    done = client.get('/api/cases/' + demo['case_id']).json()
    listing = next(case for case in client.get('/api/cases').json() if case['id'] == demo['case_id'])
    assert done['status'] == 'completed'
    assert done['duration_seconds'] == done['runs'][0]['duration_seconds'] == listing['duration_seconds'] == 65.5
    assert done['started_at'].endswith('+00:00') and done['finished_at'].endswith('+00:00')
    exported = client.get(f"/api/cases/{demo['case_id']}/runs/{demo['run_id']}/export").json()
    assert exported['timing']['duration_seconds'] == 65.5


def test_failed_run_records_finish_and_stops_its_timer(client, baseline, monkeypatch):
    demo = cached_demo(client, baseline)
    clock = [datetime(2026, 11, 14, 11, tzinfo=timezone.utc)]
    monkeypatch.setattr(pipeline, 'now', lambda: clock[0])
    monkeypatch.setattr(timing, 'now', lambda: clock[0])
    pipeline.claim()
    clock[0] += timedelta(seconds=7)
    def fail(*args):
        raise RuntimeError('Deliberate reconciliation failure')
    monkeypatch.setattr(pipeline, 'reconcile', fail)
    pipeline.process(demo['run_id'])
    clock[0] += timedelta(hours=1)
    case = client.get('/api/cases/' + demo['case_id']).json()
    assert case['status'] == 'failed' and case['duration_seconds'] == 7
    assert case['finished_at'] is not None


def test_retries_preserve_first_start_and_exhaustion_records_finish(client, monkeypatch):
    clock = [datetime(2026, 11, 14, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(pipeline, 'now', lambda: clock[0])
    with Session.begin() as session:
        case = Case(title='Retry timer', context={})
        session.add(case)
        session.flush()
        run = Run(case_id=case.id)
        session.add(run)
        session.flush()
        run_id = run.id
    for _ in range(3):
        assert pipeline.claim() == run_id
        with Session.begin() as session:
            run = session.get(Run, run_id)
            assert timing.timestamp(run.started_at) == datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
            run.lease_until = clock[0] - timedelta(seconds=1)
        clock[0] += timedelta(seconds=30)
    assert pipeline.claim() is None
    with Session() as session:
        run = session.get(Run, run_id)
        assert run.status == 'failed' and timing.run_timing(run)['duration_seconds'] == 90


def test_legacy_run_migration_preserves_data_and_does_not_invent_duration(tmp_path, monkeypatch):
    legacy = create_engine('sqlite:///' + (tmp_path/'legacy.db').as_posix())
    try:
        with legacy.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE runs (id VARCHAR(36) PRIMARY KEY, status VARCHAR(30), payload JSON)')
            connection.exec_driver_sql("INSERT INTO runs VALUES ('legacy', 'completed', '{\"keep\":true}')")
        monkeypatch.setattr(db, 'engine', legacy)
        db.init_db()
        db.init_db()
        assert {'started_at', 'finished_at'} <= {column['name'] for column in inspect(legacy).get_columns('runs')}
        with legacy.connect() as connection:
            row = connection.exec_driver_sql('SELECT status, payload, started_at, finished_at FROM runs').one()
            assert row == ('completed', '{"keep":true}', None, None)
        assert timing.run_timing(Run(status='completed'))['duration_seconds'] is None
    finally:
        legacy.dispose()
