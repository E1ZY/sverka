"""Pure reconciliation. No parsers, database access, filenames or answer workbook."""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RULES = json.loads(Path(__file__).with_name('rules.json').read_text(encoding='utf-8'))
ARTICLES = RULES['articles']


def money(value):
    if value is None:
        return None
    result = Decimal(str(value).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
    if not result.is_finite():
        raise InvalidOperation('Non-finite amount')
    return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def classify(text):
    text = text.lower().replace('ё', 'е')
    scores = {code: sum(1 for p in rule['patterns'] if p.replace('ё', 'е') in text) for code, rule in ARTICLES.items()}
    best = max(scores.values())
    winners = [code for code, score in scores.items() if score == best]
    return winners[0] if best and len(winners) == 1 else None


def reconcile(context, documents):
    docs = copy.deepcopy(documents)
    findings, included, seen_hash, seen_business = [], [], {}, {}
    uncertain = False
    report_docs = [d for d in docs if d['role'] == 'report']
    report = (report_docs[0].get('extraction') or {}) if len(report_docs) == 1 else {}
    report_values = report.get('report_values', {})
    report_evidence = report.get('report_evidence', {})
    start, end = date.fromisoformat(context['period_start']), date.fromisoformat(context['period_end'])

    for doc in docs:
        if doc['role'] != 'primary':
            continue
        fact = doc.get('extraction') or {}
        issue = None
        detail = ''
        duplicate_of = None
        if doc.get('error'):
            issue, detail = 'EXTRACTION_ERROR', doc['error']
            uncertain = True
        elif doc['sha256'] in seen_hash:
            issue, detail = 'DUPLICATE', 'Байтовая копия уже представленного документа.'
            duplicate_of = seen_hash[doc['sha256']]
        else:
            seen_hash[doc['sha256']] = doc['id']
            if not fact.get('contract') or not fact.get('period_start') or not fact.get('period_end') or fact.get('amount') is None:
                issue, detail = 'MISSING_FIELDS', 'Не удалось достоверно извлечь договор, период или сумму.'
                uncertain = True
            elif fact['contract'] != context['contract']:
                issue, detail = 'WRONG_CONTRACT', f"Договор {fact['contract']} вместо {context['contract']}."
            elif date.fromisoformat(fact['period_end']) < start or date.fromisoformat(fact['period_start']) > end:
                issue, detail = 'OUT_OF_PERIOD', 'Период операции находится вне проверяемого интервала.'
            elif date.fromisoformat(fact['period_start']) < start or date.fromisoformat(fact['period_end']) > end:
                issue, detail = 'PERIOD_OVERLAP', 'Период частично пересекает проверяемый. Требуется распределение суммы.'
                uncertain = True
            elif fact.get('needs_review'):
                issue, detail = 'LOW_CONFIDENCE', 'Результат распознавания требует подтверждения.'
                uncertain = True
            elif fact.get('article') not in ARTICLES:
                issue, detail = 'AMBIGUOUS_LINK', 'Назначение операции не позволяет однозначно выбрать статью.'
                uncertain = True
            else:
                key = (fact.get('number'), fact.get('document_date'), fact['contract'], fact.get('counterparty', '').casefold())
                if key[0] and key[1] and key[3] and key in seen_business:
                    previous = seen_business[key]
                    if money(previous['extraction']['amount']) == money(fact['amount']):
                        issue, detail = 'DUPLICATE', 'Совпадают номер, дата, договор, контрагент и сумма.'
                        duplicate_of = previous['id']
                    else:
                        issue, detail = 'CONFLICTING_DOCUMENT', 'Совпадают реквизиты, но суммы различаются. Требуется проверка обоих документов.'
                        uncertain = True
                else:
                    seen_business[key] = doc
        if issue:
            findings.append({'type': issue, 'document_id': doc['id'], 'name': doc['name'], 'detail': detail, 'duplicate_of': duplicate_of})
            doc['disposition'] = issue
        else:
            doc['disposition'] = 'INCLUDED'
            included.append(doc)

    # Conflicting revisions cannot leave the earlier amount silently included.
    conflict_ids = set()
    for issue in findings:
        if issue['type'] == 'CONFLICTING_DOCUMENT':
            source = next(d for d in docs if d['id'] == issue['document_id'])['extraction']
            for d in included:
                f = d['extraction']
                if all(f.get(k) == source.get(k) for k in ('number', 'document_date', 'contract', 'counterparty')):
                    conflict_ids.add(d['id'])
                    d['disposition'] = 'CONFLICTING_DOCUMENT'
    included = [d for d in included if d['id'] not in conflict_ids]

    results = []
    for code, rule in ARTICLES.items():
        sources = [d for d in included if d['extraction']['article'] == code]
        partial = sum((money(d['extraction']['amount']) for d in sources), Decimal('0'))
        actual = money(report_values.get(code))
        reason = None
        if code in ('0200', '0300'):
            month = date(start.year, start.month, 1)
            expected_months = set()
            while month <= end:
                expected_months.add(month.strftime('%Y-%m'))
                month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
            months = [d['extraction']['period_start'][:7] for d in sources]
            missing_months = sorted(expected_months-set(months))
            if missing_months:
                findings.append({'type':'MISSING_DOCUMENT', 'document_id':report_docs[0]['id'] if report_docs else '',
                                 'article':code, 'detail':f'{code}: нет расчётных документов за {", ".join(missing_months)}.'})
        if not sources:
            reason = 'Не найдены подтверждающие операции.'
        elif uncertain:
            reason = 'В комплекте есть неразрешённые документы. Полнота агрегата не подтверждена.'
        elif code in ('0200', '0300'):
            if set(months) != expected_months or len(months) != len(set(months)):
                reason = 'Нет единственного расчётного документа для каждого месяца периода.'
        if not context.get('complete_package', False):
            reason = 'Комплект не заявлен полным. Рассчитана только подтверждённая часть.'
        if actual is None or report.get('needs_review'):
            reason = 'Значение или строка КФЗ не распознаны уверенно.'
        if report.get('contract') != context['contract']:
            reason = 'Договор итогового отчёта не подтверждён или не совпадает с контекстом.'
        expected = partial if reason is None else None
        delta = actual - expected if actual is not None and expected is not None else None
        status = 'INSUFFICIENT_DATA' if reason else ('MATCH' if delta == 0 else 'MISMATCH')
        results.append({'code': code, 'name': rule['name'], 'actual': str(actual) if actual is not None else None,
                        'expected': str(expected) if expected is not None else None, 'confirmed_subtotal': str(partial),
                        'delta': str(delta) if delta is not None else None, 'status': status, 'reason': reason,
                        'report_evidence': report_evidence.get(code),
                        'terms': [{'document_id': d['id'], 'name': d['name'], 'amount': d['extraction']['amount'],
                                   'evidence': d['extraction'].get('amount_evidence'), 'classification_evidence': d['extraction'].get('classification_evidence'),
                                   'calculation': d['extraction'].get('calculation'), 'reviewed': d['extraction'].get('reviewed', False)} for d in sources]})
    actual = money(report_values.get('total'))
    complete = all(r['expected'] is not None for r in results) and actual is not None
    expected = sum((money(r['expected']) for r in results), Decimal('0')) if complete else None
    delta = actual - expected if expected is not None else None
    results.append({'code': 'total', 'name': 'Итого по проверяемой строке', 'actual': str(actual) if actual is not None else None,
                    'expected': str(expected) if expected is not None else None,
                    'delta': str(delta) if delta is not None else None, 'status': 'INSUFFICIENT_DATA' if not complete else ('MATCH' if delta == 0 else 'MISMATCH'),
                    'reason': None if complete else 'Не все входящие статьи подтверждены.', 'terms': [], 'report_evidence': report_evidence.get('total')})
    # Internal arithmetic is independent of confirmation by source documents.
    if actual is not None and all(r['actual'] is not None for r in results[:-1]):
        report_sum = sum((money(r['actual']) for r in results[:-1]), Decimal('0'))
        if report_sum != actual:
            findings.append({'type': 'REPORT_ARITHMETIC', 'document_id': report_docs[0]['id'], 'detail': f'Сумма верхних статей {report_sum} не равна итогу {actual}.'})
    unverified = [{**item, 'status': 'INSUFFICIENT_DATA'} for item in RULES['unverifiable']]
    return {'metrics': results, 'unverified': unverified, 'findings': findings, 'documents': docs,
            'summary': {'matched': sum(r['status'] == 'MATCH' for r in results), 'mismatched': sum(r['status'] == 'MISMATCH' for r in results),
                        'unverified': sum(r['status'] == 'INSUFFICIENT_DATA' for r in results) + len(unverified),
                        'included_documents': len(included), 'excluded_documents': len(findings),
                        'scope': 'Сверка с предоставленным комплектом документов. Полнота бухгалтерского учёта за его пределами не проверялась.'}}
