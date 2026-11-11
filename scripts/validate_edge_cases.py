"""Validate generated inputs through upload API + worker using an isolated DB."""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',help='Validate one case ID')
    args=parser.parse_args()
    (ROOT/'.runtime').mkdir(exist_ok=True)
    database=Path(tempfile.mkdtemp(prefix='edge-validation-',dir=ROOT/'.runtime'))
    os.environ['DATA_DIR']=str(database)
    os.environ['DATABASE_URL']='sqlite:///'+(database/'validation.db').as_posix()
    os.environ['EMBED_WORKER']='false'
    from fastapi.testclient import TestClient
    from app.main import app
    from scripts.edge_case_support import run_fixture
    catalog=json.loads((ROOT/'cases/catalog.json').read_text(encoding='utf-8'))
    cases=[c for c in catalog['cases'] if args.only is None or c['id']==args.only]
    if not cases:
        parser.error('Unknown case ID')
    results=[]
    with TestClient(app) as client:
        for item in cases:
            try:
                result=run_fixture(client,ROOT/'cases'/item['manifest'])
            except Exception as exc:
                result={'failures':[type(exc).__name__+': '+str(exc)]}
            if item['known_limitation']:
                status='KNOWN_LIMITATION' if result['failures'] else 'UNEXPECTED_PASS'
            else:
                status='FAIL' if result['failures'] else 'PASS'
            results.append({'id':item['id'],'title':item['title'],'status':status,'known_limitation':item['known_limitation'],**result})
            print(f'{status:17} {item["id"]}',flush=True)
            if result['failures'] and not item['known_limitation']:
                print('\n'.join(result['failures'][:8]),flush=True)
    output={'created_at':datetime.now(timezone.utc).isoformat(),'cases':results,
            'summary':{status:sum(c['status']==status for c in results) for status in ['PASS','KNOWN_LIMITATION','FAIL','UNEXPECTED_PASS']}}
    target=ROOT/'cases/validation.local.json'
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(output['summary'])
    print('Saved: '+str(target))
    return 1 if output['summary']['FAIL'] or output['summary']['UNEXPECTED_PASS'] else 0


if __name__=='__main__':
    raise SystemExit(main())
