"""Two aligned cost trees. No reference workbook values enter the calculation."""
from decimal import Decimal

from .domain import money
from .card_metadata import card_metadata
from .document_validation import validation_log

CATEGORIES = [
    ('materials', 'Материальные затраты', [(4, 'Материальные затраты')]),
    ('0200', 'Оплата труда', [(7, 'Основная заработная плата'), (8, 'Дополнительная заработная плата'), (9, 'Резерв отпусков и взносов')]),
    ('0300', 'Обязательное социальное страхование', [(12, 'Основная заработная плата: взносы'), (13, 'Дополнительная заработная плата: взносы'), (14, 'Резерв отпусков: взносы')]),
    ('0800', 'Общепроизводственные затраты', [(15, 'Общепроизводственные расходы')]),
    ('0900', 'Общехозяйственные затраты', [(16, 'Общехозяйственные расходы')]),
]
# Missing proof is a warning; an established discrepancy takes precedence.
WEIGHTS = {'MATCH': 1, 'INSUFFICIENT_DATA': 2, 'UNALLOCATED': 2, 'MISMATCH': 3}


def amount_sum(values):
    values = list(values)
    return str(sum((money(value) for value in values), Decimal('0'))) if values and all(v is not None for v in values) else None


def build_cost_tree(context, result):
    if not result or not isinstance(result.get('documents'), list):
        return None
    report = next((doc for doc in result['documents'] if doc['role'] == 'report'), {})
    fact = report.get('extraction') or {}
    rows = fact.get('cost_rows', [])
    stage, selected_year = context['stage'], int(context['period_start'][:4])
    periods = sorted({row['year'] for row in rows if row['stage'] == stage and row['year']} | {selected_year})
    metrics = {metric['code']: metric for metric in result['metrics']}

    def leaf(code, column, year):
        row = next((row for row in rows if row['stage'] == stage and row['year'] == year), {})
        value = row.get('values', {}).get(str(column))
        evidence = row.get('evidence', {}).get(str(column))
        metric = metrics.get(code, {})
        # Only single-column categories can inherit the existing confirmed aggregate.
        expected = metric.get('expected') if column in (15, 16) and year == selected_year else None
        if value is None and column in (15, 16) and year == selected_year:
            value, evidence = metric.get('actual'), metric.get('report_evidence')
        status = 'INSUFFICIENT_DATA' if value is None or expected is None else ('MATCH' if money(value) == money(expected) else 'MISMATCH')
        if value is None:
            reason = 'НЕПРОВЕРЕНО: заявленная сумма этой строки не распознана в карточке.'
        elif expected is None:
            reason = 'НЕПРОВЕРЕНО: ' + ('нет распределения документов по подкатегории.' if column not in (15, 16) else 'нет подтверждения за этот период.')
        else:
            reason = 'Заявленная сумма отличается от суммы по принятым документам.' if status == 'MISMATCH' else None
        return {'id': f'{code}.{column}.{year}',
                'name': f'{stage} этап · {year}',
                'code': str(column), 'actual': value, 'expected': expected, 'status': status,
                'delta': str(money(value)-money(expected)) if value is not None and expected is not None else None,
                'evidence': evidence, 'report_id': report.get('id'),
                'reason': reason,
                'sources': metric.get('terms', []) if expected is not None else [], 'children': []}

    def parent(identifier, name, children, code=''):
        actual = amount_sum(child['actual'] for child in children if not child.get('allocation'))
        expected = amount_sum(child['expected'] for child in children)
        partial = [child.get('expected') if child.get('expected') is not None else child.get('confirmed_subtotal') for child in children]
        partial = [value for value in partial if value is not None]
        status = max((child['status'] for child in children), key=lambda s: WEIGHTS[s], default='INSUFFICIENT_DATA')
        if status == 'MISMATCH':
            problem = next(child for child in children if child['status'] == 'MISMATCH')
            reason = f'Есть расхождение в дочерней строке «{problem["name"]}». Разверните ветку для просмотра расчёта.'
        elif status in ('INSUFFICIENT_DATA', 'UNALLOCATED'):
            reason = 'НЕПРОВЕРЕНО: не все дочерние строки обеспечены подтверждением или разбивкой. Это не доказывает расхождение сумм.'
        else:
            reason = None
        return {'id': identifier, 'code': code, 'name': name, 'actual': actual, 'expected': expected, 'status': status,
                'delta': str(money(actual)-money(expected)) if actual is not None and expected is not None else None,
                'children': children, 'sources': [], 'confirmed_subtotal': amount_sum(partial), 'reason': reason}

    categories = []
    for code, name, columns in CATEGORIES:
        children = []
        for column, title in columns:
            subtotal = parent(f'{code}.{column}.total', f'Всего {stage} этап', [leaf(code, column, year) for year in periods])
            children.append(parent(f'{code}.{column}', title, [subtotal], str(column)))
        metric = metrics.get(code, {})
        if code in ('0200', '0300') and metric.get('terms'):
            children.append({'id': code+'.unallocated', 'code': '', 'name': f'Принятые документы за {selected_year} без разбивки по подкатегориям',
                             'actual': None, 'expected': metric.get('confirmed_subtotal'), 'status': 'UNALLOCATED',
                             'allocation': True, 'children': [], 'sources': metric['terms'],
                             'reason': 'НЕПРОВЕРЕНО: есть принятые документы по статье, но их распределение по подкатегориям не подтверждено.'})
        categories.append(parent(code, name, children, '' if code == 'materials' else code))
    root = parent('stage', f'{stage} этап', categories)
    return {'root': root, 'periods': periods, 'metadata': fact.get('business_metadata') or card_metadata([{'text': fact.get('text', ''), 'page': 1}]),
            'document_validation': result.get('document_validation') or validation_log(context, result),
            'note': 'Деревья включают только распознанные годовые строки проверяемого этапа. Документы проверяются за выбранный период сверки. Неизвестные суммы не заменяются нулём. Принятые документы без разбивки по подкатегориям показаны отдельной веткой; их сумма подтверждена только частично.'}
