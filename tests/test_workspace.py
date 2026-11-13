import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy import select

from app.card_metadata import card_metadata
from app.cost_tree import build_cost_tree
from app.db import Case, Document, DocumentAsset, Run, Session
from app.domain import reconcile
from app.pipeline import document_dict

CONTEXT = {'contract': '26/01/01-77', 'stage': 3, 'period_start': '2026-01-01', 'period_end': '2026-01-31', 'complete_package': True}


def pdf_bytes():
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 40), 'Workspace integration fixture ' + uuid4().hex)
        return pdf.tobytes()


def make_case(client):
    case = client.post('/api/cases', json={**CONTEXT, 'title': 'Сверка реестра'}).json()
    content = pdf_bytes()
    docs = []
    for role in ('report', 'primary'):
        response = client.post(f"/api/cases/{case['id']}/documents", data={'role': role}, files=[('files', (role+'.pdf', content, 'application/pdf'))])
        assert response.status_code == 201, response.text
        docs.extend(response.json())
    return case['id'], docs


def complete_case(case_id):
    with Session.begin() as session:
        case = session.get(Case, case_id)
        docs = session.scalars(select(Document).where(Document.case_id == case_id)).all()
        for doc in docs:
            common = {'contract': CONTEXT['contract'], 'period_start': CONTEXT['period_start'], 'period_end': CONTEXT['period_end'], 'business_metadata': {}}
            doc.extraction = {**common, **({'report_values': {'0200': '0', '0300': '0', '0800': '25000', '0900': '0', 'total': '25000'}} if doc.role == 'report' else {'article': '0800', 'amount': '25000'})}
        result = reconcile(case.context, [document_dict(doc) for doc in docs])
        run = Run(case_id=case_id, status='completed', payload=result)
        session.add(run)
        session.flush()
        case.active_run_id, case.status = run.id, 'completed'


def test_copy_keeps_original_and_can_use_changed_document_selection(client):
    source, docs = make_case(client)
    complete_case(source)
    before = client.get('/api/cases/'+source).json()
    response = client.post(f'/api/cases/{source}/copy', json={**CONTEXT, 'title': 'Изменённая копия', 'document_ids': [doc['id'] for doc in docs]})
    assert response.status_code == 201, response.text
    target = response.json()
    assert target['id'] != source and target['status'] == 'draft'
    copied = client.get('/api/cases/'+target['id']).json()
    assert len(copied['documents']) == 2
    assert {doc['id'] for doc in copied['documents']}.isdisjoint({doc['id'] for doc in docs})
    assert client.get('/api/cases/'+source).json() == before
    assert target['context']['copied_from'] == source
    assert target['status_changed_at']


def test_copy_cannot_take_documents_from_another_case(client):
    source, _ = make_case(client)
    other, docs = make_case(client)
    response = client.post(f'/api/cases/{source}/copy', json={**CONTEXT, 'document_ids': [docs[0]['id']]})
    assert response.status_code == 400


def test_registry_retains_unlinked_originals_and_cleanup_preserves_shared_files(client):
    source, docs = make_case(client)
    target = client.post(f'/api/cases/{source}/copy', json={**CONTEXT, 'document_ids': [doc['id'] for doc in docs]}).json()['id']
    registry = client.get('/api/documents')
    assert registry.status_code == 200, registry.text
    sha = docs[0]['sha256']
    item = next(item for item in registry.json() if item['id'] == sha)
    assert {source, target} <= {link['id'] for link in item['cases']}
    original = client.get(f'/api/documents/{sha}/original').content
    assert client.request('DELETE', '/api/cases', json={'case_ids': [source]}).status_code == 200
    assert client.get(f'/api/documents/{sha}/original').content == original
    assert client.request('DELETE', '/api/cases', json={'case_ids': [target], 'delete_unlinked_documents': False}).status_code == 200
    # Other tests may intentionally share a hash, so detach only this fixture's assets.
    with Session() as session:
        remaining = session.scalars(select(Document).where(Document.sha256 == sha)).all()
    assert not remaining
    assert next(item for item in client.get('/api/documents').json() if item['id'] == sha)['cases'] == []
    assert sha in client.delete('/api/documents/unlinked').json()['deleted_ids']
    assert client.get(f'/api/documents/{sha}/original').status_code == 404


def test_package_contains_real_originals_and_reconciliation_result(client):
    case_id, docs = make_case(client)
    assert client.get(f'/api/cases/{case_id}/package.zip').status_code == 409
    complete_case(case_id)
    response = client.get(f'/api/cases/{case_id}/package.zip')
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        entries = [name for name in archive.namelist() if name.startswith('documents/')]
        assert len(entries) == 2
        assert all(archive.read(name).startswith(b'%PDF') for name in entries)
        result = json.loads(archive.read('reconciliation.json'))
        assert result['case_id'] == case_id and result['cost_tree']['root']['name'] == '3 этап'
        assert '25000' in archive.read('reconciliation.csv').decode('utf-8-sig')
    with Session() as session:
        case = session.get(Case, case_id)
        assert case.status == 'completed'


def test_card_metadata_uses_document_values_and_keeps_missing_values_unknown():
    text = 'Карточка учета фактических затрат № 3/1\nОтчётный период: Август 2025 г. — май 2026 г.\nИсполнитель: МФТИ, Физтех\nЗаказчик: ООО «СПЦ»\nНачало 3 этапа: 16 августа 2025 г.\nОкончание 3 этапа: 30 мая 2026 г.\nОснование: Составная часть НИР\nКонтракт: № 24/03/15-01 от 09.04.2024 г.\nФПС: 10064.15.02.X1458\nПолучено средств за 3 этап: 10 862 418,06\nСинтетический счёт и субсчёт: 109.60\nСметная стоимость 3 этапа, утвержденная: 13 578 022,58'
    fields = card_metadata([{'text': text, 'page': 1}])
    assert fields['card_number']['value'] == '3/1'
    assert fields['customer']['value'] == 'ООО «СПЦ»'
    assert fields['fps']['value'] == '10064.15.02.X1458'
    assert fields['funds_received']['value'] == '10 862 418,06'
    assert fields['approved_estimate']['value'] == '13 578 022,58'
    assert all(field['value'] is None for field in card_metadata([]).values())


def test_tree_excludes_reference_stage_and_propagates_strictest_status():
    columns = {str(column): '0.00' for column in (4,7,8,9,12,13,14,15,16)}
    docs = [{'id':'r', 'name':'r.pdf', 'role':'report', 'extraction': {'cost_rows': [
        {'stage':2,'year':None,'values':{**columns,'15':'9000000'}},
        {'stage':3,'year':2025,'values':{**columns,'15':'10'}},
        {'stage':3,'year':2026,'values':{**columns,'15':'20'}},
    ]}}]
    metrics = [{'code':'0800','actual':'20','expected':'19','terms':[]}]
    tree = build_cost_tree(CONTEXT, {'documents':docs,'metrics':metrics,'findings':[]})
    assert tree['root']['actual'] == '30.00'
    assert tree['root']['expected'] is None
    assert tree['root']['status'] == 'INSUFFICIENT_DATA'
    branch = next(node for node in tree['root']['children'] if node['id']=='0800')
    assert branch['status'] == 'INSUFFICIENT_DATA'  # missing 2025 outranks the 2026 mismatch
    assert branch['children'][0]['children'][1]['reference'] is True
    assert branch['children'][0]['children'][0]['children'][1]['status'] == 'MISMATCH'


def test_explicit_party_mismatch_is_excluded_and_explained():
    from app.document_validation import validation_log
    common = {'contract': CONTEXT['contract'], 'period_start':CONTEXT['period_start'],'period_end':CONTEXT['period_end']}
    docs = [
        {'id':'r','name':'r.pdf','sha256':'r','role':'report','extraction':{**common,'report_values':{},'business_metadata':{'customer':{'value':'Заказчик А'}}}},
        {'id':'d','name':'d.pdf','sha256':'d','role':'primary','extraction':{**common,'article':'0800','amount':'100','business_metadata':{'document_name': {'value':'Карточка учета фактических затрат'}, 'customer':{'value':'Заказчик Б'}}}},
    ]
    result = reconcile(CONTEXT, docs)
    assert result['documents'][1]['disposition'] == 'METADATA_MISMATCH'
    assert result['summary']['included_documents'] == 0
    log = validation_log(CONTEXT, result)
    assert log[1]['verdict'] == 'Отклонено'
    assert 'Заказчик' in log[1]['reason']


@pytest.mark.parametrize(('expected', 'status'), [('20.00', 'MATCH'), ('19.00', 'MISMATCH'), (None, 'INSUFFICIENT_DATA')])
def test_parent_uses_child_status_priority(monkeypatch, expected, status):
    import app.cost_tree as module
    monkeypatch.setattr(module, 'CATEGORIES', [('0800','Производственные',[(15,'Расходы')])])
    result = {'documents':[{'id':'r','name':'r.pdf','role':'report','extraction':{'cost_rows':[{'stage':3,'year':2026,'values':{'15':'20.00'}}]}}],
              'metrics':[{'code':'0800','actual':'20.00','expected':expected,'terms':[]}], 'findings':[]}
    assert module.build_cost_tree(CONTEXT, result)['root']['status'] == status


def test_party_roles_and_uncertain_ocr_do_not_cause_false_rejection():
    from app.card_metadata import party_conflict, party_comparison
    report = {'business_metadata': {'executor': {'value':'МФТИ', 'status':'found'}}}
    supplier = {'business_metadata': {'executor': {'value':'ООО Поставщик', 'status':'found'}}}
    assert not party_conflict(report, supplier)
    uncertain_card = {'business_metadata': {'document_name': {'value':'Карточка'}, 'executor': {'value':'МФТ1', 'status':'uncertain'}}}
    assert not party_conflict(report, uncertain_card)
    assert any(check['status']=='UNCERTAIN' for check in party_comparison(report['business_metadata'], uncertain_card['business_metadata']))


def test_existing_database_migration_keeps_legacy_cases(tmp_path, monkeypatch):
    import app.db as db
    from sqlalchemy import create_engine, inspect
    engine = create_engine('sqlite:///' + (tmp_path/'legacy.db').as_posix())
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE cases (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200), context JSON, status VARCHAR(30), created_at DATETIME, active_run_id VARCHAR(36))')
            connection.exec_driver_sql("INSERT INTO cases VALUES ('legacy', 'keep', '{}', 'completed', '2026-01-01', NULL)")
        monkeypatch.setattr(db, 'engine', engine)
        db.init_db()
        db.init_db()
        assert 'status_changed_at' in {column['name'] for column in inspect(engine).get_columns('cases')}
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT title, status, status_changed_at FROM cases WHERE id='legacy'").one() == ('keep','completed',None)
    finally:
        engine.dispose()
