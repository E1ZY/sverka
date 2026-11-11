"""Fixture inputs and a post-run oracle comparison, separate from calculation."""
import json
import re
from collections import Counter

from fastapi import HTTPException

from .config import DEMO_DIR, FIXTURES_DIR, MAX_CASE_FILES, MAX_FILE_BYTES, ROOT
from .domain import ARTICLES
from .extractors import SUPPORTED, digest

ORIGINAL_FIXTURE_ID = 'original_task_data'


def original_manifest():
    source = json.loads((ROOT/'demo'/'manifest.json').read_text(encoding='utf-8'))
    return {
        'id': ORIGINAL_FIXTURE_ID, 'title': 'Исходный комплект задания', 'origin': 'task',
        'description': 'Отчёт КФЗ и первичные документы из task/data: январь–май 2026 года. '
                       'Проверяются расхождение в сумме, дубликат, документ вне периода и другой договор.',
        'context': source['context'], 'known_limitation': None,
        'files': [{'path': item['name'], 'role': item['role']} for item in source['files']],
    }


def catalog():
    path = FIXTURES_DIR/'catalog.json'
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding='utf-8'))['cases']


def load_fixture(fixture_id):
    if fixture_id == ORIGINAL_FIXTURE_ID:
        if not DEMO_DIR.is_dir():
            raise HTTPException(404, 'Исходные документы задания не установлены')
        return DEMO_DIR.resolve(), original_manifest()
    if not re.fullmatch(r'[a-z0-9_]{1,80}', fixture_id) or not any(item['id'] == fixture_id for item in catalog()):
        raise HTTPException(404, 'Тестовый кейс не найден')
    directory = (FIXTURES_DIR/'generated'/fixture_id).resolve()
    if not directory.is_relative_to((FIXTURES_DIR/'generated').resolve()):
        raise HTTPException(400, 'Недопустимый путь кейса')
    path = directory/'case.json'
    if not path.is_file():
        raise HTTPException(404, 'Комплект тестовых документов не установлен')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('id') != fixture_id:
        raise HTTPException(409, 'Идентификатор кейса не совпадает с каталогом')
    return directory, manifest


def list_fixtures():
    result = []
    ids = ([ORIGINAL_FIXTURE_ID] if DEMO_DIR.is_dir() else []) + [item['id'] for item in catalog()]
    for fixture_id in ids:
        _, manifest = load_fixture(fixture_id)
        result.append({k: manifest.get(k) for k in ('id', 'title', 'description', 'context', 'known_limitation')} |
                      {'input_files': len(manifest['files']), 'origin': manifest.get('origin', 'generated')})
    return result


def fixture_inputs(fixture_id):
    directory, manifest = load_fixture(fixture_id)
    input_directory = directory if fixture_id == ORIGINAL_FIXTURE_ID else (directory/'input').resolve()
    files = manifest['files']
    if len(files) > MAX_CASE_FILES or sum(f['role'] == 'report' for f in files) != 1 or not any(f['role'] == 'primary' for f in files):
        raise HTTPException(400, 'Некорректный состав тестового комплекта')
    inputs = []
    for item in files:
        source = (directory/item['path']).resolve()
        if not source.is_relative_to(input_directory) or not source.is_file():
            raise HTTPException(400, 'Входной файл не найден в каталоге кейса')
        if item['role'] not in {'report', 'primary'} or source.suffix.lower() not in SUPPORTED:
            raise HTTPException(400, 'Неподдерживаемый формат тестового документа')
        if item['role'] == 'report' and source.suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg'}:
            raise HTTPException(400, 'Неподдерживаемый формат итогового отчёта')
        if not 0 < source.stat().st_size <= MAX_FILE_BYTES:
            raise HTTPException(400, 'Недопустимый размер тестового документа')
        sha = digest(source)
        if fixture_id != ORIGINAL_FIXTURE_ID and sha != item['sha256']:
            raise HTTPException(409, 'Файлы кейса изменились. Перегенерируйте комплект или загрузите его вручную.')
        inputs.append((source, item['role'], sha))
    return manifest, inputs


def load_oracle(fixture_id):
    directory, _ = load_fixture(fixture_id)
    path = ROOT/'demo'/'expected.json' if fixture_id == ORIGINAL_FIXTURE_ID else directory/'expected.json'
    return json.loads(path.read_text(encoding='utf-8'))


def compare_fixture(fixture_id, payload):
    """Observer only. Called after a completed run; never alters its payload."""
    try:
        _, manifest = load_fixture(fixture_id)
        expected = load_oracle(fixture_id)
    except (HTTPException, OSError, ValueError):
        return {'available': False, 'matches': None, 'differences': [], 'message': 'Эталон кейса сейчас недоступен.'}
    actual_metrics = {m['code']: m for m in payload['metrics']}
    differences = []
    field_names = {'actual': 'В отчёте', 'expected': 'По документам', 'delta': 'Разница', 'status': 'Статус'}
    for code, metric in expected['metrics'].items():
        name = ARTICLES[code]['name'] if code in ARTICLES else 'Итого'
        for field, value in metric.items():
            actual = actual_metrics.get(code, {}).get(field)
            if actual != value:
                differences.append({'label': f'{code} · {name} · {field_names[field]}', 'kind': 'status' if field == 'status' else 'money',
                                    'expected': value, 'actual': actual})
    counts = Counter(f['type'] for f in payload['findings'])
    required = expected['required_findings']
    categories = set(required) | (set(counts) if expected['exact_findings'] else set())
    for category in sorted(categories):
        if counts[category] != required.get(category, 0):
            differences.append({'label': 'Замечания · '+category, 'kind': 'count',
                                'expected': required.get(category, 0), 'actual': counts[category]})
    report = next((d for d in payload['documents'] if d['role'] == 'report'), {})
    if bool(report.get('error')) != expected['report_extraction_error']:
        differences.append({'label': 'Ошибка чтения итогового отчёта', 'kind': 'boolean',
                            'expected': expected['report_extraction_error'], 'actual': bool(report.get('error'))})
    return {'available': True, 'fixture_id': fixture_id, 'title': manifest['title'],
            'known_limitation': manifest.get('known_limitation'), 'matches': not differences,
            'differences': differences, 'run_id': payload['run_id']}
