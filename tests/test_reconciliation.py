import copy
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from app.domain import money, reconcile

ROOT = Path(__file__).resolve().parent.parent


def recalculate(baseline, mutate):
    result = copy.deepcopy(baseline['result'])
    mutate(result)
    return reconcile(result['context'], result['documents'])


def test_full_dataset_against_independent_answer_workbook(baseline):
    # The answer workbook is imported here only; never in app/ or demo manifest.
    sheet = load_workbook(ROOT/'task/данные/!Правильные_ответы_и_разбор.xlsx', data_only=True)['Эталон']
    metrics = baseline['result']['metrics']
    for metric, row in zip(metrics, range(4, 9)):
        assert money(metric['actual']) == money(sheet[f'B{row}'].value)
        assert money(metric['expected']) == money(sheet[f'C{row}'].value)
        assert money(metric['delta']) == money(sheet[f'D{row}'].value)
    assert [m['status'] for m in metrics] == ['MATCH', 'MATCH', 'MISMATCH', 'MATCH', 'MISMATCH']
    assert {f['type'] for f in baseline['result']['findings']} == {'DUPLICATE', 'OUT_OF_PERIOD', 'WRONG_CONTRACT'}
    assert baseline['result']['summary']['included_documents'] == 19


def test_every_term_has_precise_source(baseline):
    for metric in baseline['result']['metrics']:
        assert metric['report_evidence']['page'] == 1
        assert len(metric['report_evidence']['bbox']) == 4
        for term in metric['terms']:
            ev = term['evidence']
            assert ev['text']
            assert ev.get('bbox') or (ev.get('sheet') and ev.get('range')) or ev.get('table')
            if ev.get('bbox'):
                assert all(0 <= x <= 1 for x in ev['bbox'])


def test_renaming_every_file_does_not_change_calculation(baseline):
    r = recalculate(baseline, lambda r: [d.update(name=f'random-{i}.bin') for i,d in enumerate(r['documents'])])
    assert [m['expected'] for m in r['metrics']] == [m['expected'] for m in baseline['result']['metrics']]


def test_missing_payroll_month_is_not_report_error(baseline):
    def mutate(r):
        r['documents'] = [d for d in r['documents'] if not (d['extraction'].get('article') == '0200' and d['extraction'].get('period_start') == '2026-01-01')]
    r = recalculate(baseline, mutate)
    assert r['metrics'][0]['status'] == 'INSUFFICIENT_DATA'
    assert r['metrics'][0]['expected'] is None
    assert r['metrics'][-1]['expected'] is None
    assert r['metrics'][1]['status'] == 'MATCH'
    assert any(f['type']=='MISSING_DOCUMENT' and f['article']=='0200' for f in r['findings'])


def test_changed_source_changes_expected_value(baseline):
    def mutate(r):
        next(d for d in r['documents'] if d['extraction'].get('amount') == '245000.00')['extraction']['amount'] = '244000.00'
    r = recalculate(baseline, mutate)
    assert r['metrics'][2]['expected'] == '1132298.10'
    assert r['metrics'][2]['delta'] == '13500.00'


def test_nonidentical_binary_copy_is_still_duplicate(baseline):
    def mutate(r):
        d = copy.deepcopy(next(d for d in r['documents'] if d['extraction'].get('number') == 'ADM-27'))
        d.update(id='rescan', sha256='new-binary-hash', name='rescan.pdf')
        r['documents'].append(d)
    r = recalculate(baseline, mutate)
    assert r['metrics'][3]['status'] == 'MATCH'
    assert sum(f['type']=='DUPLICATE' for f in r['findings']) == 2


def test_conflicting_versions_require_review(baseline):
    def mutate(r):
        d = copy.deepcopy(next(d for d in r['documents'] if d['extraction'].get('number') == 'ADM-27'))
        d.update(id='revision', sha256='revision-hash')
        d['extraction']['amount'] = '500000.00'
        r['documents'].append(d)
    r = recalculate(baseline, mutate)
    assert any(f['type']=='CONFLICTING_DOCUMENT' for f in r['findings'])
    assert r['metrics'][3]['expected'] is None
    assert all(t['amount'] not in {'487500.00','500000.00'} for t in r['metrics'][3]['terms'])


def test_incomplete_package_has_no_false_matches(baseline):
    r = recalculate(baseline, lambda r:r['context'].update(complete_package=False))
    assert all(m['status']=='INSUFFICIENT_DATA' for m in r['metrics'])
    assert r['metrics'][0]['confirmed_subtotal'] == '5558474.83'


def test_unreadable_document_is_not_silently_dropped(baseline):
    def mutate(r):
        r['documents'].append({'id':'bad','role':'primary','name':'broken.pdf','sha256':'broken','error':'Повреждённый PDF','extraction':None})
    r = recalculate(baseline, mutate)
    assert any(f['type']=='EXTRACTION_ERROR' for f in r['findings'])
    assert all(m['expected'] is None for m in r['metrics'])


def test_missing_report_value_does_not_become_zero(baseline):
    def mutate(r):
        next(d for d in r['documents'] if d['role']=='report')['extraction']['report_values']['0300'] = None
    r = recalculate(baseline, mutate)
    assert r['metrics'][1]['status'] == 'INSUFFICIENT_DATA'
    assert r['metrics'][1]['actual'] is None
    assert r['metrics'][0]['status'] == 'MATCH'


def test_decimal_rounding_and_signed_corrections():
    assert money('1 234,565') == Decimal('1234.57')
    assert money('-0.015') == Decimal('-0.02')
    assert money(0) == Decimal('0.00')


def test_all_primary_document_numbers_are_extracted(baseline):
    for doc in baseline['result']['documents']:
        if doc['role'] == 'primary':
            assert doc['extraction'].get('number'), doc['name']


def test_real_zero_is_confirmed_when_coverage_is_complete(baseline):
    def mutate(r):
        for d in r['documents']:
            if d['role']=='report':
                d['extraction']['report_values'] = {k:'0.00' for k in d['extraction']['report_values']}
            else:
                d['extraction']['amount'] = '0.00'
    r = recalculate(baseline, mutate)
    assert all(m['status']=='MATCH' for m in r['metrics'])
    assert all(m['expected']=='0.00' for m in r['metrics'])
