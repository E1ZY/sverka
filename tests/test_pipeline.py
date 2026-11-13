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
