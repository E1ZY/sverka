"""Apply audited KФЗ corrections without changing the original OCR extraction."""
import copy
import re

from .domain import RULES, money

REPORT_CODES = tuple(RULES['report_columns'])
DIRECT_COLUMNS = {'0800': '15', '0900': '16'}


def parse_amount(value):
    compact = re.sub(r'\s', '', value).replace('−', '-')
    if not re.fullmatch(r'-?\d+(?:[.,]\d{1,2})?', compact):
        raise ValueError('Укажите сумму с точностью до копейки, например 1 234,56.')
    try:
        return str(money(compact))
    except ArithmeticError:
        raise ValueError('Сумма слишком велика для расчёта.') from None


def apply_report_changes(extraction, changes, context):
    fact = copy.deepcopy(extraction or {})
    year = int(context['period_start'][:4])
    values = fact.setdefault('report_values', {})
    evidence = fact.setdefault('report_evidence', {})
    rows = fact.setdefault('cost_rows', [])
    cells = copy.deepcopy(changes.get('cost_cells', []))
    for code, value in changes.get('report_values', {}).items():
        values[code] = value
        evidence[code] = {**(evidence.get(code) or {}), 'source': 'manual', 'manual_value': value}
        if code in DIRECT_COLUMNS:
            cells.append({'year': year, 'column': DIRECT_COLUMNS[code], 'amount': value})
    for cell in cells:
        row = next((row for row in rows if row['stage'] == context['stage'] and row['year'] == cell['year']), None)
        if row is None:
            row = {'stage': context['stage'], 'year': cell['year'], 'values': {}, 'evidence': {}}
            rows.append(row)
        row.setdefault('values', {})[cell['column']] = cell['amount']
        locators = row.setdefault('evidence', {})
        locators[cell['column']] = {**(locators.get(cell['column']) or {}), 'source': 'manual', 'manual_value': cell['amount']}
    if 'contract' in changes:
        fact['contract'] = changes['contract']
        fields = fact.setdefault('business_metadata', {})
        fields['contract'] = {**fields.get('contract', {}), 'label': 'Контракт',
                              'value': changes['contract'], 'status': 'found',
                              'evidence': {'source': 'manual', 'text': changes['contract']}}
    # A correction to one cell must not confirm other uncertain amounts.
    fact['needs_review'] = any(values.get(code) is None or
        ((evidence.get(code) or {}).get('source') != 'manual' and
         ((evidence.get(code) or {}).get('confidence', 0) < 45 or not extraction))
        for code in REPORT_CODES)
    fact['reviewed'] = True
    return fact


def apply_document_changes(document, changes, context):
    if document['role'] == 'report':
        document['extraction'] = apply_report_changes(document.get('extraction'), changes, context)
        # Recovery from failed OCR requires explicit confirmation of every total
        # and the contract; partial edits retain the extraction error.
        fact = document['extraction']
        if document.get('error') and not fact['needs_review'] and fact.get('contract'):
            fact['original_extraction_error'] = document['error']
            document['error'] = None
    else:
        document['extraction'] = copy.deepcopy(document.get('extraction') or {})
        document['extraction'].update(changes)
        document['extraction'].update(needs_review=False, reviewed=True)
