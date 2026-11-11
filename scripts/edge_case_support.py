"""Integration harness shared by pytest and the standalone fixture validator."""
import json
import hashlib
from collections import Counter
from pathlib import Path


def run_fixture(client, manifest_path):
    # The HTTP request gets input files + user-supplied context only. The oracle
    # stays in this test process and is never submitted to the application.
    from app.pipeline import claim, process
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    directory=manifest_path.parent
    oracle=json.loads((directory/'expected.json').read_text(encoding='utf-8'))
    failures=[]
    for item in manifest['files']:
        source=(directory/item['path']).resolve()
        if not source.is_relative_to(directory.resolve()):
            raise ValueError('Input escapes fixture directory')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:
            failures.append('Input checksum changed: '+item['path'])
    context={k:v for k,v in manifest['context'].items() if k!='row_label'}
    created=client.post('/api/cases',json={'title':'Edge '+manifest['id'],**context})
    if created.status_code!=201:
        return {'failures':failures+['Create failed: '+created.text]}
    case_id=created.json()['id']
    upload_status=201
    for role in ['report','primary']:
        uploads=[]
        for item in manifest['files']:
            if item['role']==role:
                source=directory/item['path']
                uploads.append(('files',(source.name,source.read_bytes())))
        uploaded=client.post(f'/api/cases/{case_id}/documents',data={'role':role},files=uploads)
        upload_status=uploaded.status_code
        target=201 if role=='report' else oracle['upload_status']
        if upload_status!=target:
            failures.append(f'{role} upload: expected HTTP {target}, got {upload_status}: {uploaded.text}')
        if upload_status!=201:
            if target!=201:
                current=client.get('/api/cases/'+case_id).json()
                if any(d['role']=='primary' for d in current['documents']):
                    failures.append('Rejected batch left primary documents in the database')
            return {'failures':failures,'upload_status':upload_status,'case_id':case_id}
    queued=client.post(f'/api/cases/{case_id}/runs')
    if queued.status_code!=202:
        return {'failures':failures+['Enqueue failed: '+queued.text],'case_id':case_id}
    run_id=claim()
    if run_id!=queued.json()['id']:
        return {'failures':failures+['Worker claimed an unexpected job'],'case_id':case_id}
    process(run_id)
    current=client.get('/api/cases/'+case_id).json()
    if current['status']!='completed' or not current['result']:
        return {'failures':failures+['Run did not complete: '+str(current.get('runs'))],'case_id':case_id}
    result=current['result']
    metrics={m['code']:m for m in result['metrics']}
    for code,expected in oracle['metrics'].items():
        for field,value in expected.items():
            actual=metrics.get(code,{}).get(field)
            if actual!=value:
                failures.append(f'{code}.{field}: expected {value!r}, got {actual!r}')
    counts=Counter(f['type'] for f in result['findings'])
    for category,count in oracle['required_findings'].items():
        if counts[category]!=count:
            failures.append(f'{category}: expected {count}, got {counts[category]}')
    if oracle['exact_findings'] and dict(counts)!=oracle['required_findings']:
        failures.append(f'Unexpected findings: {dict(counts)!r}')
    report=next(d for d in result['documents'] if d['role']=='report')
    if bool(report.get('error'))!=oracle['report_extraction_error']:
        failures.append('Unexpected report extraction state: '+str(report.get('error')))
    return {'failures':failures,'upload_status':upload_status,'case_id':case_id,
            'metrics':{code:{k:m.get(k) for k in ['actual','expected','delta','status']} for code,m in metrics.items()},
            'findings':dict(counts)}
