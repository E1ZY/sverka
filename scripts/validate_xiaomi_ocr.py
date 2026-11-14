"""Run real Xiaomi OCR on the diagnostic image corpus, saving raw text and strict comparisons."""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from PIL import ImageOps

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
MONEY=re.compile(r'(?<![\d/.,])[-−]?(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)[,.]\d{2}(?![\d/.,])')


def plain(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', text))).strip()


def amounts(text):
    return [str(Decimal(re.sub(r'[ \u00a0\u202f]', '', value).replace(',', '.').replace('−','-')))
            for value in MONEY.findall(plain(text))]


def compare_full_text(text, expected):
    content=plain(text)
    missing_codes=[code for code in expected['codes']
                   if not re.search(r'(?<![\d.,])'+re.escape(code)+r'(?!\d|[.,]\d)',content)]
    recognized=amounts(text)
    wanted=[*expected['values'],expected['total']]
    missing_values=[value for value in wanted if Decimal(value) not in [Decimal(item) for item in recognized]]
    return {'matches':not missing_codes and not missing_values,'missing_codes':missing_codes,
            'missing_values':missing_values,'recognized_amounts':recognized,
            'scope':'Presence of exact codes and amounts; full-page column association is not assumed.'}


def compare_regions(code_text, value_text, expected):
    codes=re.findall(r'(?<![\d.,])\d{3,5}(?!\d|[.,]\d)',plain(code_text))
    values=amounts(value_text)
    wanted=[*expected['values'],expected['total']]
    values_match=len(values)==len(wanted) and all(Decimal(a)==Decimal(b) for a,b in zip(values,wanted))
    return {'matches':codes==expected['codes'] and values_match,'codes_match':codes==expected['codes'],
            'values_match':values_match,'recognized_codes':codes,'expected_codes':expected['codes'],
            'recognized_values':values,'expected_values':wanted,
            'scope':'Exact left-to-right header codes and current-year amounts in independently bounded table regions.'}


def compare_profile(fact, expected):
    actual=fact.get('report_values',{})
    differences=[{'field':code,'expected':value,'actual':actual.get(code)}
                 for code,value in expected['report_values'].items()
                 if actual.get(code) is None or Decimal(actual[code])!=Decimal(value)]
    if fact.get('contract')!=expected['contract']:
        differences.append({'field':'contract','expected':expected['contract'],'actual':fact.get('contract')})
    return {'matches':not differences and not fact.get('needs_review',True),
            'differences':differences,'needs_review':fact.get('needs_review'),
            'report_values':actual,'contract':fact.get('contract'),
            'scope':'The unchanged application KФЗ extractor, including confidence and contract checks.'}


def model_text(tokens):
    lines=[]
    for token in tokens:
        if not lines or lines[-1][0]!=token['line']:
            lines.append((token['line'],[]))
        lines[-1][1].append(token['text'])
    return '\n'.join(' '.join(parts) for _,parts in lines)


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def compare_saved(corpus, output):
    """Re-evaluate saved model answers without running inference or accepting stale inputs."""
    report=json.loads((output/'results.json').read_text(encoding='utf-8'))
    for case in report['cases']:
        manifest_path=corpus/case['id']/'case.json'
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        image=manifest_path.parent/manifest['input']
        if case.get('input_sha256')!=hashlib.sha256(image.read_bytes()).hexdigest():
            raise ValueError('Saved answer belongs to a different input: '+case['id'])
        expected=json.loads(manifest_path.with_name('expected.json').read_text(encoding='utf-8'))
        if case.get('full_page',{}).get('raw_text'):
            text=(output/case['full_page']['raw_text']).read_text(encoding='utf-8')
            case['full_page'].update(compare_full_text(text,expected))
        if 'regions' in case and 'error' not in case['regions']:
            codes=(output/(case['id']+'.codes.txt')).read_text(encoding='utf-8')
            values=(output/(case['id']+'.current_values.txt')).read_text(encoding='utf-8')
            case['regions'].update(compare_regions(codes,values,expected))
        if 'profile' in case and 'error' not in case['profile']:
            fact=json.loads((output/(case['id']+'.extraction.json')).read_text(encoding='utf-8'))
            case['profile'].update(compare_profile(fact,expected))
        case['matches']=case.get('full_page',{}).get('matches',False) and case.get('regions',case.get('profile',{})).get('matches',False)
    report['evaluation_version']=2
    report['summary']={'cases':len(report['cases']),'passed':sum(case['matches'] for case in report['cases']),
                       'failed':sum(not case['matches'] for case in report['cases'])}
    write_json(output/'results.json',report)
    return report['summary']


def recognize(image, settings, output, stem, psm=6, numeric=False):
    from app.xiaomi_ocr import words
    started=time.perf_counter()
    tokens=words(image,settings,psm=psm,numeric=numeric)
    seconds=time.perf_counter()-started
    text=model_text(tokens)
    (output/(stem+'.txt')).write_text(text,encoding='utf-8')
    write_json(output/(stem+'.tokens.json'),tokens)
    return text,{'seconds':round(seconds,3),'tokens':len(tokens),
                 'min_confidence':min((token['confidence'] for token in tokens),default=None),
                 'raw_text':stem+'.txt','raw_tokens':stem+'.tokens.json'}


def evaluate_case(manifest_path, settings, output):
    from app.extractors import extract_report, page_image
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    image_path=manifest_path.parent/manifest['input']
    if hashlib.sha256(image_path.read_bytes()).hexdigest()!=manifest['sha256']:
        raise ValueError('Input checksum does not match the fixture manifest.')
    expected=json.loads((manifest_path.parent/'expected.json').read_text(encoding='utf-8'))
    image=page_image(image_path)
    result={'id':manifest['id'],'kind':manifest['kind'],'input':str(image_path.relative_to(ROOT)),
            'input_sha256':manifest['sha256'],'size':image.size,'quality':manifest['quality']}
    started=time.perf_counter()
    print(f"CASE {manifest['id']} | full image {image.size}",flush=True)
    try:
        text,details=recognize(image,settings,output,manifest['id']+'.full')
        result['full_page']={**details,**compare_full_text(text,expected)}
        print(f"  full image: {result['full_page']['matches']} ({details['seconds']}s)",flush=True)
    except Exception as error:
        result['full_page']={'matches':False,'error':type(error).__name__+': '+str(error)}
        print('  full image ERROR: '+str(error),flush=True)
    if manifest['kind']=='synthetic':
        try:
            texts={}
            timings={}
            for name,box in manifest['regions'].items():
                crop=image.crop(tuple(round(coordinate*image.size[index%2]) for index,coordinate in enumerate(box)))
                crop=ImageOps.expand(crop,border=12,fill='white')
                texts[name],timings[name]=recognize(crop,settings,output,manifest['id']+'.'+name,psm=7,
                                                  numeric=name=='current_values')
            result['regions']={**compare_regions(texts['codes'],texts['current_values'],expected),'timings':timings}
            print(f"  table regions: {result['regions']['matches']}",flush=True)
        except Exception as error:
            result['regions']={'matches':False,'error':type(error).__name__+': '+str(error)}
            print('  table regions ERROR: '+str(error),flush=True)
    else:
        print('  application KФЗ extraction',flush=True)
        profile_start=time.perf_counter()
        try:
            fact=extract_report(image_path,manifest['context'],progress=lambda text,fraction:print('    '+text,flush=True))
            write_json(output/(manifest['id']+'.extraction.json'),fact)
            result['profile']={**compare_profile(fact,expected),'seconds':round(time.perf_counter()-profile_start,3)}
        except Exception as error:
            result['profile']={'matches':False,'error':type(error).__name__+': '+str(error),
                               'seconds':round(time.perf_counter()-profile_start,3)}
            print('  application extractor ERROR: '+str(error),flush=True)
    result['seconds']=round(time.perf_counter()-started,3)
    result['matches']=result['full_page']['matches'] and result.get('regions',result.get('profile',{})).get('matches',False)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only')
    parser.add_argument('--device',choices=['cuda','cpu'],default='cuda')
    parser.add_argument('--corpus',type=Path,default=ROOT/'cases/ocr')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/xiaomi-ocr-validation')
    parser.add_argument('--compare-only',action='store_true',help='Compare saved answers again without loading the model.')
    args=parser.parse_args()
    if args.compare_only:
        summary=compare_saved(args.corpus,args.output)
        print(json.dumps(summary))
        return 1 if summary['failed'] else 0
    os.environ['OCR_PROVIDER']='xiaomi'
    os.environ['XIAOMI_OCR_DEVICE']=args.device
    from app.ocr_settings import OCRSettings
    from app.ocr import provenance
    import torch
    if args.device=='cuda' and not torch.cuda.is_available():
        parser.error('CUDA is unavailable. This GPU test does not silently fall back to CPU.')
    settings=replace(OCRSettings.from_env(),device=args.device)
    catalog=json.loads((args.corpus/'catalog.json').read_text(encoding='utf-8'))
    chosen=[item for item in catalog['cases'] if args.only is None or item['id']==args.only]
    if not chosen:
        parser.error('Unknown OCR fixture ID.')
    args.output.mkdir(parents=True,exist_ok=True)
    report={'started_at':datetime.now(timezone.utc).isoformat(),'evaluation_version':2,'ocr':provenance(),
            'torch':torch.__version__,'device':args.device,'gpu':torch.cuda.get_device_name(0) if args.device=='cuda' else None,
            'implementation':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                              for name in ('app/xiaomi_ocr.py','app/extractors.py')},'cases':[]}
    started=time.perf_counter()
    for item in chosen:
        try:
            result=evaluate_case(args.corpus/item['manifest'],settings,args.output)
        except Exception as error:
            result={'id':item['id'],'matches':False,'error':type(error).__name__+': '+str(error)}
        report['cases'].append(result)
        write_json(args.output/'results.json',report)
    report['seconds']=round(time.perf_counter()-started,3)
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    report['summary']={'cases':len(chosen),'passed':sum(case['matches'] for case in report['cases']),
                       'failed':sum(not case['matches'] for case in report['cases'])}
    if args.device=='cuda':
        report['peak_model_allocated_mib']=round(torch.cuda.max_memory_allocated()/1024**2,1)
    write_json(args.output/'results.json',report)
    print(json.dumps(report['summary']),flush=True)
    print('Saved: '+str(args.output/'results.json'),flush=True)
    return 1 if report['summary']['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
