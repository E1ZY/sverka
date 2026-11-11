from app.pipeline import claim, process
import json
from pathlib import Path
from datetime import timedelta
from app.db import Run, Session, now


def test_health_and_case_lookup(client):
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/cases/does-not-exist').status_code == 404


def test_context_validation(client):
    r = client.post('/api/cases', json={'title':'Invalid','contract':'x','stage':3,'period_start':'2026-05-01','period_end':'2026-01-01'})
    assert r.status_code == 422


def test_duplicate_enqueue_is_rejected(client):
    demo = client.post('/api/demo').json()
    assert client.post('/api/cases/'+demo['case_id']+'/runs').status_code == 409
    process(claim())


def test_download_preview_export_and_case_isolation(client, baseline):
    case_id = baseline['id']
    report = next(d for d in baseline['documents'] if d['role']=='report')
    page = client.get(f'/api/cases/{case_id}/documents/{report["id"]}/page/1')
    assert page.status_code == 200 and page.content.startswith(b'\x89PNG')
    assert client.get(f'/api/cases/{case_id}/documents/{report["id"]}/page/999').status_code == 400
    assert client.get(f'/api/cases/{case_id}/documents/{report["id"]}/original').content.startswith(b'%PDF')
    assert client.get(f'/api/cases/wrong/documents/{report["id"]}/original').status_code == 404
    r = client.get(f'/api/cases/{case_id}/runs/{baseline["active_run_id"]}/export?format=csv')
    assert r.status_code == 200 and '12500.00' in r.text


def test_review_preserves_original_and_previous_run(client, baseline):
    case_id = baseline['id']
    old_run = baseline['active_run_id']
    source = next(d for d in baseline['documents'] if (d.get('extraction') or {}).get('amount') == '245000.00')
    r = client.post(f'/api/cases/{case_id}/documents/{source["id"]}/review', json={'amount':'244000.00','reason':'Проверено бухгалтером по оригиналу'})
    assert r.status_code == 201, r.text
    process(claim())
    updated = client.get('/api/cases/'+case_id).json()
    assert updated['active_run_id'] != old_run
    assert updated['result']['metrics'][2]['delta'] == '13500.00'
    raw = next(d for d in updated['documents'] if d['id']==source['id'])
    assert raw['extraction']['amount'] == '245000.00'
    old = client.get(f'/api/cases/{case_id}/runs/{old_run}/export').json()
    assert old['metrics'][2]['delta'] == '12500.00'
    assert updated['reviews'][0]['before']['amount'] == '245000.00'


def test_corrupt_zip_is_rejected_and_rolled_back(client):
    c = client.post('/api/cases', json={'title':'Upload test','contract':'x','stage':1,'period_start':'2026-01-01','period_end':'2026-01-31'}).json()
    r = client.post(f'/api/cases/{c["id"]}/documents',data={'role':'primary'},files=[('files',('broken.xlsx',b'not-a-zip'))])
    assert r.status_code == 400
    assert client.get('/api/cases/'+c['id']).json()['documents'] == []


def test_nan_correction_rejected(client, baseline):
    source = next(d for d in baseline['documents'] if d['role']=='primary')
    r = client.post(f'/api/cases/{baseline["id"]}/documents/{source["id"]}/review',json={'amount':'NaN','reason':'Некорректная сумма'})
    assert r.status_code == 422


def test_custom_multipart_uploads_with_renamed_files(client):
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root/'demo/manifest.json').read_text(encoding='utf-8'))
    context = {k:v for k,v in manifest['context'].items() if k!='row_label'}
    case = client.post('/api/cases', json={'title':'Загрузка через API',**context}).json()
    for role in ['report','primary']:
        files = [('files', (f'input-{i}{Path(item["name"]).suffix}', (root/'task/data'/item['name']).read_bytes()))
                 for i,item in enumerate(manifest['files']) if item['role']==role]
        r = client.post(f'/api/cases/{case["id"]}/documents',data={'role':role},files=files)
        assert r.status_code == 201, r.text
    assert client.post(f'/api/cases/{case["id"]}/runs').status_code == 202
    process(claim())
    updated = client.get('/api/cases/'+case['id']).json()
    assert updated['status'] == 'completed'
    assert updated['result']['metrics'][-1]['delta'] == '12500.00'
    assert updated['result']['summary']['included_documents'] == 19


def test_expired_worker_lease_is_recovered(client):
    demo = client.post('/api/demo').json()
    first = claim()
    assert first == demo['run_id']
    with Session.begin() as session:
        run = session.get(Run, first)
        run.lease_until = now()-timedelta(seconds=1)
    recovered = claim()
    assert recovered == first
    process(recovered)
    case = client.get('/api/cases/'+demo['case_id']).json()
    assert case['status'] == 'completed'
    assert case['result']['metrics'][-1]['delta']=='12500.00'
