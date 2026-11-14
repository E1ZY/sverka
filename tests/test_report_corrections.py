from copy import deepcopy

import pytest
from sqlalchemy import select

from app import pipeline
from app.db import Case, Document, Review, Run, Session


@pytest.fixture
def report_case(client, baseline):
    demo = client.post('/api/demo').json()
    facts = {doc['name']: deepcopy(doc['extraction']) for doc in baseline['result']['documents']}
    with Session.begin() as session:
        for doc in session.scalars(select(Document).where(Document.case_id == demo['case_id'])):
            doc.extraction = facts[doc.name]
    assert pipeline.claim() == demo['run_id']
    pipeline.process(demo['run_id'])
    case = client.get('/api/cases/' + demo['case_id']).json()
    report = next(doc for doc in case['documents'] if doc['role'] == 'report')
    return case, report


def submit(client, case, report, **changes):
    return client.post(f'/api/cases/{case["id"]}/documents/{report["id"]}/report-review',
                       json={'reason': 'Значения проверены по оригиналу КФЗ', **changes})


def complete(client, case, response):
    assert response.status_code == 201, response.text
    assert pipeline.claim() == response.json()['run_id']
    pipeline.process(response.json()['run_id'])
    result = client.get('/api/cases/' + case['id']).json()
    assert result['status'] == 'completed'
    return result


def test_fill_missing_total_preserves_raw_ocr_previous_run_and_source_location(client, report_case):
    case, report = report_case
    with Session.begin() as session:
        doc = session.get(Document, report['id'])
        fact = deepcopy(doc.extraction)
        fact['report_values']['0800'] = None
        fact['needs_review'] = True
        doc.extraction = fact
    updated = complete(client, case, submit(client, case, report, report_values={'0800': '1 145 798,10'}))
    assert updated['result']['metrics'][2]['actual'] == '1145798.10'
    assert updated['result']['metrics'][2]['delta'] == '12500.00'
    assert next(doc for doc in updated['documents'] if doc['id'] == report['id'])['extraction']['report_values']['0800'] is None
    effective = next(doc for doc in updated['result']['documents'] if doc['id'] == report['id'])['extraction']
    assert effective['report_evidence']['0800']['source'] == 'manual'
    assert effective['report_evidence']['0800']['bbox'] == report['extraction']['report_evidence']['0800']['bbox']
    assert next(row for row in effective['cost_rows'] if row['year'] == 2026)['values']['15'] == '1145798.10'
    assert updated['reviews'][0]['before']['report_values'] == {'0800': None}
    assert updated['reviews'][0]['created_at'].endswith('+00:00')
    assert all(run['created_at'].endswith('+00:00') for run in updated['runs'])
    old = client.get(f'/api/cases/{case["id"]}/runs/{case["active_run_id"]}/export').json()
    assert old == case['result']


def test_partial_edits_merge_without_confirming_other_missing_values(client, report_case):
    case, report = report_case
    with Session.begin() as session:
        doc = session.get(Document, report['id'])
        fact = deepcopy(doc.extraction)
        fact['report_values'].update({'0800': None, '0900': None})
        fact['needs_review'] = True
        doc.extraction = fact
    first = complete(client, case, submit(client, case, report, report_values={'0800': '0'}))
    metrics = {item['code']: item for item in first['result']['metrics']}
    assert metrics['0800']['actual'] == '0.00' and metrics['0900']['actual'] is None
    assert all(item['status'] == 'INSUFFICIENT_DATA' for item in metrics.values())
    second = complete(client, case, submit(client, case, report, report_values={'0900': '3204744,51'}))
    assert second['result']['metrics'][2]['actual'] == '0.00'
    assert second['result']['metrics'][3]['actual'] == '3204744.51'
    assert second['result']['metrics'][3]['status'] == 'MATCH'
    assert second['reviews'][1]['before']['report_values'] == {'0900': None}


def test_manual_detail_does_not_invent_aggregate_or_prove_allocation(client, report_case):
    case, report = report_case
    updated = complete(client, case, submit(client, case, report,
        cost_cells=[{'year': 2026, 'column': '7', 'amount': '123,45'}]))
    effective = next(doc for doc in updated['result']['documents'] if doc['role'] == 'report')['extraction']
    row = next(row for row in effective['cost_rows'] if row['year'] == 2026)
    assert row['values']['7'] == '123.45'
    assert effective['report_values']['0200'] == report['extraction']['report_values']['0200']
    salary = next(node for node in updated['cost_tree']['root']['children'] if node['code'] == '0200')
    assert salary['status'] == 'INSUFFICIENT_DATA'


def test_failed_ocr_can_be_recovered_only_after_all_totals_and_contract_are_confirmed(client, report_case, monkeypatch):
    case, report = report_case
    def unreadable(*args, **kwargs):
        raise RuntimeError('Не найдена сетка КФЗ')
    monkeypatch.setattr(pipeline, 'extract_report', unreadable)
    with Session.begin() as session:
        doc = session.get(Document, report['id'])
        doc.extraction, doc.error = None, 'Не найдена сетка КФЗ'
    partial = complete(client, case, submit(client, case, report, report_values={'0800': '1,00'}))
    assert all(item['status'] == 'INSUFFICIENT_DATA' for item in partial['result']['metrics'])
    restored = complete(client, case, submit(client, case, report,
        report_values=report['extraction']['report_values'], contract=case['context']['contract']))
    fact = next(doc for doc in restored['result']['documents'] if doc['role'] == 'report')
    assert fact['error'] is None
    assert fact['extraction']['original_extraction_error'] == 'Не найдена сетка КФЗ'
    assert restored['result']['metrics'][2]['delta'] == '12500.00'
    assert next(doc for doc in restored['documents'] if doc['role'] == 'report')['error']


@pytest.mark.parametrize('changes', [
    {'report_values': {'0800': 'NaN'}}, {'report_values': {'0800': 'Infinity'}},
    {'report_values': {'0800': '1.001'}}, {'report_values': {'0800': '1e5'}},
    {'report_values': {'0800': '9' * 80}}, {'report_values': {'invalid': '10'}},
    {'cost_cells': [{'year': 2025, 'column': '7', 'amount': '1'}]},
    {'cost_cells': [{'year': 2026, 'column': '17', 'amount': '1'}]},
    {'cost_cells': [{'year': 2026, 'column': '7', 'amount': '1'}] * 2},
    {'report_values': {'0800': '10'}, 'cost_cells': [{'year': 2026, 'column': '15', 'amount': '20'}]},
    {'contract': ' '}, {'report_values': {'0800': '1'}, 'reason': '     '},
])
def test_invalid_report_edits_do_not_create_a_review_or_run(client, report_case, changes):
    case, report = report_case
    response = submit(client, case, report, **changes)
    assert response.status_code == 422, response.text
    after = client.get('/api/cases/' + case['id']).json()
    assert after['active_run_id'] == case['active_run_id']
    assert after['reviews'] == []


def test_report_corrections_do_not_follow_copy_to_different_annual_row(client, report_case):
    case, report = report_case
    complete(client, case, submit(client, case, report, report_values={'0800': '7'}))
    source = client.get('/api/cases/' + case['id']).json()
    body = {**case['context'], 'title': 'Other annual row', 'period_start': '2025-01-01', 'period_end': '2025-05-31',
            'document_ids': [doc['id'] for doc in source['documents']]}
    response = client.post('/api/cases/' + case['id'] + '/copy', json=body)
    assert response.status_code == 201
    copy = client.get('/api/cases/' + response.json()['id']).json()
    assert copy['reviews'] == []


def test_stale_case_state_cannot_enqueue_duplicate_run(client):
    with Session.begin() as session:
        case = Case(title='Concurrent enqueue', context={})
        session.add(case)
        session.flush()
        case_id = case.id
    with Session() as stale:
        old_case = stale.get(Case, case_id)
        with Session.begin() as session:
            pipeline.enqueue(session, session.get(Case, case_id))
        with pytest.raises(ValueError, match='уже выполняется'):
            pipeline.enqueue(stale, old_case)
        stale.rollback()
    with Session.begin() as session:
        runs = session.scalars(select(Run).where(Run.case_id == case_id)).all()
        assert len(runs) == 1
        runs[0].status = 'failed'
        session.get(Case, case_id).status = 'failed'
