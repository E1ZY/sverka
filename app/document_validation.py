"""Explain the inclusion decision stored in each immutable reconciliation result."""
from .card_metadata import party_comparison


def validation_log(context, result):
    report = next((doc for doc in result['documents'] if doc['role'] == 'report'), {})
    report_meta = (report.get('extraction') or {}).get('business_metadata', {})
    output = []
    for doc in result['documents']:
        fact = doc.get('extraction') or {}
        findings = [finding for finding in result['findings'] if finding.get('document_id') == doc['id'] and finding['type'] != 'MISSING_DOCUMENT']
        primary = doc['role'] == 'primary'
        accepted = doc.get('disposition') == 'INCLUDED' if primary else not doc.get('error') and not fact.get('needs_review') and fact.get('contract') == context['contract']
        checks = [
            {'field': 'Договор', 'value': fact.get('contract'), 'expected': context['contract'],
             'status': 'MATCH' if fact.get('contract') == context['contract'] else 'MISMATCH' if fact.get('contract') else 'MISSING'},
            {'field': 'Период', 'value': f"{fact.get('period_start') or '—'} — {fact.get('period_end') or '—'}",
             'expected': f"{context['period_start']} — {context['period_end']}",
             'status': ('MATCH' if context['period_start'] <= fact['period_start'] <= fact['period_end'] <= context['period_end'] else 'MISMATCH') if fact.get('period_start') and fact.get('period_end') else 'MISSING'},
        ]
        checks.extend(party_comparison(report_meta, fact.get('business_metadata', {})))
        if primary:
            for field, label in (('number', 'Номер документа'), ('amount', 'Сумма'), ('article', 'Статья затрат')):
                value = fact.get(field)
                checks.append({'field': label, 'value': value, 'expected': None, 'status': 'EXTRACTED' if value is not None else 'MISSING'})
        reason = '; '.join(finding['detail'] for finding in findings) or doc.get('error')
        if not reason:
            reason = ('Договор и период соответствуют; сумма и статья определены; дубликатов нет.' if primary else 'Главный отчёт выбран как основание сверки.') if accepted else 'Реквизиты или строка отчёта не подтверждены.'
        output.append({'id': doc['id'], 'name': doc['name'], 'role': doc['role'], 'article': fact.get('article'),
                       'period': (fact.get('period_start') or '')[:7] or 'Период не определён', 'amount': fact.get('amount'),
                       'accepted': accepted, 'verdict': 'Принято' if accepted else 'Отклонено', 'reason': reason,
                       'checks': checks, 'metadata': fact.get('business_metadata', {})})
    return output
