from copy import deepcopy
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app import pipeline
from app.db import Document, Session
from app.extractors import REPORT_PARSER_VERSION


@pytest.mark.parametrize('cached_parser', ['kfz-grid-v1', REPORT_PARSER_VERSION])
def test_recalculate_refreshes_outdated_report_but_keeps_current_review_gate(
        client, baseline, monkeypatch, cached_parser):
    demo = client.post('/api/demo').json()
    facts = {doc['name']: deepcopy(doc['extraction']) for doc in baseline['result']['documents']}
    fresh_report = deepcopy(next(doc['extraction'] for doc in baseline['result']['documents']
                                 if doc['role'] == 'report'))
    assert fresh_report['parser'] == REPORT_PARSER_VERSION
    assert fresh_report['needs_review'] is False

    with Session.begin() as session:
        documents = session.scalars(select(Document).where(Document.case_id == demo['case_id'])).all()
        for doc in documents:
            fact = facts[doc.name]
            if doc.role == 'report':
                fact.update(parser=cached_parser, needs_review=True)
                for evidence in fact['report_evidence'].values():
                    evidence['confidence'] = 0
            doc.extraction = fact

    report_extractor = Mock(return_value=fresh_report)
    primary_extractor = Mock(side_effect=AssertionError('Cached primary must be reused'))
    monkeypatch.setattr(pipeline, 'extract_report', report_extractor)
    monkeypatch.setattr(pipeline, 'extract_primary', primary_extractor)
    run_id = pipeline.claim()
    assert run_id == demo['run_id']
    pipeline.process(run_id)
    case = client.get('/api/cases/' + demo['case_id']).json()

    assert case['status'] == 'completed', case
    primary_extractor.assert_not_called()
    metrics = case['result']['metrics']
    if cached_parser != REPORT_PARSER_VERSION:
        report_extractor.assert_called_once()
        assert [metric['status'] for metric in metrics] == [
            'MATCH', 'MATCH', 'MISMATCH', 'MATCH', 'MISMATCH']
        assert metrics[2]['delta'] == '12500.00'
    else:
        report_extractor.assert_not_called()
        assert all(metric['status'] == 'INSUFFICIENT_DATA' for metric in metrics)
        assert all(metric['expected'] is None for metric in metrics)


def test_changing_ocr_provider_reextracts_inputs_and_preserves_previous_run(client, baseline, monkeypatch):
    demo = client.post('/api/demo').json()
    facts = {doc['name']: deepcopy(doc['extraction']) for doc in baseline['result']['documents']}
    with Session.begin() as session:
        for doc in session.scalars(select(Document).where(Document.case_id == demo['case_id'])):
            doc.extraction = {**facts[doc.name], 'ocr_signature': 'tesseract-v1'}
    before = deepcopy(client.get('/api/cases/'+baseline['id']).json()['result'])
    report = Mock(side_effect=lambda path, context: deepcopy(next(doc['extraction'] for doc in baseline['result']['documents'] if doc['role'] == 'report')))
    # Uploaded paths use generated names: resolve them through the document table.
    with Session() as session:
        paths = {doc.path: facts[doc.name] for doc in session.scalars(select(Document).where(Document.case_id == demo['case_id']))}
    primary = Mock(side_effect=lambda path: deepcopy(paths[path]))
    monkeypatch.setattr(pipeline.ocr, 'signature', lambda: 'xiaomi-test-revision')
    monkeypatch.setattr(pipeline, 'extract_report', report)
    monkeypatch.setattr(pipeline, 'extract_primary', primary)
    run_id = pipeline.claim()
    assert run_id == demo['run_id']
    pipeline.process(run_id)
    case = client.get('/api/cases/'+demo['case_id']).json()
    assert case['status'] == 'completed'
    report.assert_called_once()
    assert primary.call_count == len({doc['sha256'] for doc in case['documents'] if doc['role'] == 'primary'})
    assert all(doc['extraction']['ocr_signature'] == 'xiaomi-test-revision' for doc in case['documents'])
    assert client.get('/api/cases/'+baseline['id']).json()['result'] == before
