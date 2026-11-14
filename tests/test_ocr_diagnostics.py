import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from scripts.validate_xiaomi_ocr import compare_full_text, compare_profile, compare_regions, compare_saved

ROOT=Path(__file__).resolve().parent.parent
CORPUS=ROOT/'cases/ocr'
CATALOG=json.loads((CORPUS/'catalog.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('item',CATALOG['cases'],ids=lambda item:item['id'])
def test_ocr_fixture_inputs_and_independent_expected_amounts(item):
    manifest_path=CORPUS/item['manifest']
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    expected=json.loads((manifest_path.parent/'expected.json').read_text(encoding='utf-8'))
    image_path=manifest_path.parent/manifest['input']
    assert image_path.resolve().is_relative_to(CORPUS.resolve())
    assert hashlib.sha256(image_path.read_bytes()).hexdigest()==manifest['sha256']
    with Image.open(image_path) as image:
        assert list(image.size)==manifest['size']
    assert sum(map(Decimal,expected['values']))==Decimal(expected['total'])
    assert all(isinstance(code,str) and code.isdigit() for code in expected['codes'])
    for box in manifest.get('regions',{}).values():
        assert 0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1


def test_full_text_matching_does_not_drop_leading_zeros_or_match_code_prefixes():
    expected={'codes':['0400','1300'],'values':['1000.01'],'total':'1000.01'}
    actual=compare_full_text('400 13000 1 000,01',expected)
    assert actual['missing_codes']==['0400','1300'] and not actual['matches']
    assert compare_full_text('<td>0400</td><td>1300</td><td>1&nbsp;000,01</td>',expected)['matches']


def test_region_matching_preserves_code_and_amount_order():
    expected={'codes':['0400','13000'],'values':['10.01','20.02'],'total':'30.03'}
    correct=compare_regions('0400 | 13000','10,01 | 20,02 | 30,03',expected)
    assert correct['matches']
    assert not compare_regions('13000 | 0400','10,01 | 20,02 | 30,03',expected)['matches']
    assert not compare_regions('0400 | 13000','20,02 | 10,01 | 30,03',expected)['matches']


def test_amounts_are_not_mistaken_for_integer_category_codes():
    expected={'codes':['400','13000'],'values':['400.01'],'total':'13000.02'}
    actual=compare_full_text('400.01 13000.02',expected)
    assert actual['missing_codes']==['400','13000']
    assert not compare_regions('400.01 13000.02','400.01 13000.02',expected)['codes_match']


def test_exact_amount_comparison_does_not_use_substrings_or_round_wrong_numbers():
    expected={'codes':['0400'],'values':['1000.01'],'total':'1000.01'}
    assert not compare_full_text('0400 11 000,01',expected)['matches']
    assert not compare_full_text('0400 1 000,10',expected)['matches']


def test_profile_comparison_rejects_wrong_amounts_and_review_required():
    expected={'report_values':{'0200':'1000.01'},'contract':'test'}
    fact={'report_values':{'0200':'1000.10'},'contract':'test','needs_review':False}
    assert not compare_profile(fact,expected)['matches']
    fact['report_values']['0200']='1000.01'
    fact['needs_review']=True
    assert not compare_profile(fact,expected)['matches']
    fact['needs_review']=False
    assert compare_profile(fact,expected)['matches']


def test_corpus_covers_requested_ids_and_the_five_digit_boundary():
    codes=set()
    for item in CATALOG['cases']:
        codes.update(json.loads((CORPUS/item['manifest']).with_name('expected.json').read_text(encoding='utf-8'))['codes'])
    assert {'0400','0500','0600','0700','1000','1100','1200','1300','13000'} <= codes
    assert {'400','700'} <= codes


def test_saved_answers_cannot_be_reused_after_the_input_file_changes(tmp_path):
    corpus=tmp_path/'corpus'
    case=corpus/'sample'
    output=tmp_path/'answers'
    case.mkdir(parents=True)
    output.mkdir()
    (case/'report.jpeg').write_bytes(b'original image bytes')
    manifest={'input':'report.jpeg'}
    expected={'codes':['0400'],'values':['10.00'],'total':'10.00'}
    (case/'case.json').write_text(json.dumps(manifest),encoding='utf-8')
    (case/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
    (output/'full.txt').write_text('0400 10,00',encoding='utf-8')
    (output/'sample.codes.txt').write_text('0400',encoding='utf-8')
    (output/'sample.current_values.txt').write_text('10,00 | 10,00',encoding='utf-8')
    report={'cases':[{'id':'sample','input_sha256':hashlib.sha256(b'original image bytes').hexdigest(),
                     'full_page':{'raw_text':'full.txt'},'regions':{}}]}
    (output/'results.json').write_text(json.dumps(report),encoding='utf-8')
    assert compare_saved(corpus,output)=={'cases':1,'passed':1,'failed':0}
    (case/'report.jpeg').write_bytes(b'different image bytes')
    with pytest.raises(ValueError,match='different input'):
        compare_saved(corpus,output)
