"""Label-based business metadata with source fragments; absent fields stay absent."""
import re

FIELDS = {
    'document_name': ('Наименование документа', r'(карточка\s+(?:уч[её]та\s+)?фактических\s+затрат)'),
    'card_number': ('Номер карточки', r'карточк[аи][^\n№]{0,70}№\s*([^\n;]+)'),
    'reporting_period': ('Отчётный период', r'((?:январ[а-я]*|феврал[а-я]*|март[а-я]*|апрел[а-я]*|ма[йяе]|июн[а-я]*|июл[а-я]*|август[а-я]*|сентябр[а-я]*|октябр[а-я]*|ноябр[а-я]*|декабр[а-я]*)[^\n]*20\d{2}[^\n]*(?:[-–—]|по)[^\n]*20\d{2}[^\n]*)'),
    'executor': ('Исполнитель', r'\bисполнитель\s*[:–-]?\s*([^\n;]+)'),
    'customer': ('Заказчик', r'\bзаказчик\s*[:;–-]?\s*([^\n;]+)'),
    'stage_start': ('Начало этапа', r'(?:начало|начал[ао]\s+выполнения)\s*(?:\d+\s*)?эта[а-я]*\s*[:–-]?\s*([^\n;]+)'),
    'stage_end': ('Окончание этапа', r'(?:окончание|конец)\s*(?:\d+\s*)?эта[а-я]*\s*[:–-]?\s*([^\n;]+)'),
    'basis': ('Основание', r'(?:\bоснование\s*[:–-]?\s*|(?=составная\s+часть))([^\n;]+)'),
    'contract': ('Контракт', r'(?:контракт|договор)(?:а|у|ом)?\s*[:№–-]?\s*([^\n;]+)'),
    'fps': ('ФПС', r'(\d{5}\.\d{2}\.\d{2}\.[A-ZА-Я]\d+)'),
    'funds_received': ('Получено средств за этап', r'получен[оы]\s+средств[а]?(?:\s+(?:за|на)\s+\d+\s+эта[а-я]*)?\s*[:–-]?\s*([\d\s\u00a0]+[,.]\d{2})'),
    'account': ('Синтетический счёт и субсчёт', r'(?:синтетический\s+сч[её]т|сч[её]т\s+и\s+субсч[её]т)[^\d\n]{0,40}(\d{2,3}\.\d{2})'),
    'approved_estimate': ('Утверждённая сметная стоимость этапа', r'сметная\s+стоимость[^\n\d]{0,30}(?:\d+\s*этапа)?[^\n\d]{0,35}([\d\s\u00a0]+[,.]\d{2})'),
}


def party_comparison(report_fields, fields):
    """Same-role comparison applies to comparable report cards, not supplier acts."""
    normalize = lambda value: re.sub(r'[^\w]', '', value.casefold().replace('ё', 'е'))
    checks = []
    for key, label in (('customer', 'Заказчик'), ('executor', 'Исполнитель')):
        left = report_fields.get(key, {})
        right = fields.get(key, {})
        if not left.get('value') or not right.get('value'):
            status = 'MISSING'
        elif left.get('status', 'found') != 'found' or right.get('status', 'found') != 'found':
            status = 'UNCERTAIN'
        elif not fields.get('document_name', {}).get('value'):
            status = 'NOT_COMPARABLE'
        else:
            status = 'MATCH' if normalize(left['value']) == normalize(right['value']) else 'MISMATCH'
        checks.append({'field': label, 'value': right.get('value'), 'expected': left.get('value'), 'status': status})
    return checks


def party_conflict(report, fact):
    return any(check['status'] == 'MISMATCH' for check in party_comparison(report.get('business_metadata', {}), fact.get('business_metadata', {})))


def card_metadata(fragments):
    output = {}
    for key, (label, pattern) in FIELDS.items():
        matches = []
        for fragment in fragments:
            match = re.search(pattern, fragment['text'], re.I)
            if match:
                value = match[1].strip()
                if key in ('executor', 'customer'):
                    value = re.split(r'\s+(?:контракт|договор|ФПС|ФЛС|ЛС)\s*[:№]', value, maxsplit=1, flags=re.I)[0].strip()
                if key in ('stage_start', 'stage_end'):
                    value = re.split(r'\s+(?:получено|синтетический)', value, maxsplit=1, flags=re.I)[0].replace('"', '').strip()
                if value and not any(item['value'] == value for item in matches):
                    matches.append({'value': value, 'evidence': fragment})
        output[key] = {'label': label, 'value': matches[0]['value'] if len(matches) == 1 else None,
                       'status': ('found' if matches[0]['evidence'].get('confidence', 100) >= 80 else 'uncertain') if len(matches) == 1 else 'ambiguous' if matches else 'missing',
                       'evidence': matches[0]['evidence'] if len(matches) == 1 else None}
        if key in ('customer', 'executor') and output[key]['value'] and re.match(r'^[«"‘\s]*000\b', output[key]['value']):
            output[key]['status'] = 'uncertain'
    return output
