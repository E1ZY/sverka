import io
import json
from pathlib import Path

import pytest
from PIL import Image

from app import report_context
from app.config import DATA
from app.report_context import context_from_fragments

ROOT = Path(__file__).resolve().parent.parent


def fields(text, confidence=100):
    return context_from_fragments([{'text': text, 'confidence': confidence}])['fields']


@pytest.mark.parametrize('text', [
    'Договор № 24/03/15-01\nЭтап: 3\nОтчётный период: с 01.01.2026 по 31.05.2026',
    'Договор от 09.04.2024 № 24/03/15-01\n3-й этап\nПериод: январь — май 2026 года',
    'Номер договора: 24 / 03 / 15 – 01\nЭтап № 3\nПериод работ: 2026-01-01 - 2026-05-31',
    'Контракт № 24/03/15-01\n3 этап\nЗа период с января 2026 г. по май 2026 года',
])
def test_explicit_parameters_are_suggested(text):
    result = fields(text)
    assert {name: field['value'] for name, field in result.items()} == {
        'contract': '24/03/15-01', 'stage': 3,
        'period_start': '2026-01-01', 'period_end': '2026-05-31',
    }
    assert all(field['status'] == 'found' for field in result.values())


def test_contract_formats_and_repeated_identical_values():
    result = fields('Договор: АБ-123/2026\nДоговор: АБ-123/2026\n3 этап\nИтого 3 этап')
    assert result['contract'] == {'value': 'АБ-123/2026', 'status': 'found'}
    assert result['stage'] == {'value': 3, 'status': 'found'}


def test_multiple_distinct_candidates_leave_fields_empty():
    result = fields('Договор № 24/03/15-01\nДоговор № 26/01/01-77\n2 этап\n3 этап\n'
                    'Период: январь - май 2026\nПериод: февраль - июнь 2026')
    assert all(field == {'value': None, 'status': 'ambiguous'} for field in result.values())


def test_ambiguity_is_resolved_per_field():
    result = fields('Этап 3\nПериод: 01.01.2026 - 31.05.2026\nПериод: 01.01.2026 - 30.06.2026')
    assert result['stage']['value'] == 3
    assert result['period_start']['value'] == '2026-01-01'
    assert result['period_end'] == {'value': None, 'status': 'ambiguous'}


def test_contract_date_and_year_do_not_become_reporting_period():
    result = fields('Договор № 24/03/15-01 от 09.04.2024\n3 этап, 2026 г.')
    assert result['contract']['value'] == '24/03/15-01'
    assert result['stage']['value'] == 3
    assert result['period_start'] == result['period_end'] == {'value': None, 'status': 'missing'}


@pytest.mark.parametrize('period', [
    'Период: 31.02.2026 - 31.05.2026',
    'Период: 31.05.2026 - 01.01.2026',
    'Период: 01.12.2025 - 31.05.2026',
    'Период: декабрь 2025 - май 2026',
    'Период: 2026 год',
])
def test_invalid_incomplete_or_unsupported_period_is_not_invented(period):
    result = fields(period)
    assert result['period_start']['value'] is None
    assert result['period_end']['value'] is None


def test_month_period_and_leap_year():
    result = fields('Период подтверждающих документов: февраль 2024 года')
    assert result['period_start']['value'] == '2024-02-01'
    assert result['period_end']['value'] == '2024-02-29'


def test_separate_period_boundaries_and_missing_end():
    result = fields('Начало отчётного периода: 01.01.2026')
    assert result['period_start']['value'] == '2026-01-01'
    assert result['period_end']['status'] == 'missing'
    result = fields('Начало периода: 31.05.2026\nКонец периода: 01.01.2026')
    assert result['period_start']['status'] == result['period_end']['status'] == 'ambiguous'


def test_unreliable_ocr_does_not_suggest_values():
    result = fields('Договор № 24/03/15-01\nЭтап: 3\nПериод: январь 2026', confidence=50)
    assert all(field == {'value': None, 'status': 'uncertain'} for field in result.values())


def test_weak_second_candidate_still_makes_a_field_ambiguous():
    result = context_from_fragments([
        {'text': 'Договор № 24/03/15-01', 'confidence': 100},
        {'text': 'Договор № 26/01/01-77', 'confidence': 50},
    ])['fields']
    assert result['contract'] == {'value': None, 'status': 'ambiguous'}


def test_stage_does_not_consume_number_from_previous_line():
    result = fields('Договор № 24/03/15-01\nЭтап: 3\nПериод: январь 2026')
    assert result['stage'] == {'value': 3, 'status': 'found'}


def test_preview_reads_real_pdf_without_creating_case_or_keeping_upload(client):
    before_cases = client.get('/api/cases').json()
    before_files = set(DATA.iterdir())
    content = (ROOT/'cases/generated/00_clean/input/report.pdf').read_bytes()
    response = client.post('/api/reports/context', files={'file': ('renamed.pdf', content)})
    assert response.status_code == 200, response.text
    result = response.json()['fields']
    assert result['contract']['value'] == '26/01/01-77'
    assert result['stage'] == {'value': None, 'status': 'ambiguous'}
    assert result['period_start']['value'] == '2026-01-01'
    assert result['period_end']['value'] == '2026-01-31'
    assert client.get('/api/cases').json() == before_cases
    assert set(DATA.iterdir()) == before_files


def test_original_scanned_kfz_suggests_contract_but_requires_scope_selection(client):
    manifest = json.loads((ROOT/'demo/manifest.json').read_text(encoding='utf-8'))
    content = (ROOT/'task/data'/manifest['files'][0]['name']).read_bytes()
    response = client.post('/api/reports/context', files={'file': ('scan.pdf', content)})
    assert response.status_code == 200, response.text
    result = response.json()['fields']
    assert result['contract'] == {'value': '24/03/15-01', 'status': 'found'}
    assert result['stage'] == {'value': None, 'status': 'ambiguous'}
    # The report spans two years and does not explicitly state the selected annual period.
    assert result['period_start']['value'] is None
    assert result['period_end']['value'] is None


def test_image_preview_uses_ocr_and_confidence_of_value_not_entire_line(client, monkeypatch):
    tokens = [
        {'text': 'Договор', 'confidence': 40, 'line': 1},
        {'text': '№', 'confidence': 40, 'line': 1},
        {'text': '24/03/15-01', 'confidence': 95, 'line': 1},
        {'text': 'Этап', 'confidence': 95, 'line': 2},
        {'text': '3', 'confidence': 95, 'line': 2},
    ]
    monkeypatch.setattr(report_context.ocr, 'words', lambda image, psm: tokens)
    content = io.BytesIO()
    Image.new('RGB', (200, 100), 'white').save(content, format='PNG')
    response = client.post('/api/reports/context', files={'file': ('scan.png', content.getvalue())})
    assert response.status_code == 200, response.text
    result = response.json()['fields']
    assert result['contract']['value'] == '24/03/15-01'
    assert result['stage']['value'] == 3
    assert result['period_start']['value'] is None


@pytest.mark.parametrize(('filename', 'content', 'status'), [
    ('report.xlsx', b'not a report', 400),
    ('report.pdf', b'', 400),
    ('report.pdf', b'broken pdf', 422),
])
def test_preview_validation_cleans_up_temporary_files(client, filename, content, status):
    before = set(DATA.iterdir())
    response = client.post('/api/reports/context', files={'file': (filename, content)})
    assert response.status_code == status
    assert set(DATA.iterdir()) == before


def test_preview_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr('app.main.MAX_FILE_BYTES', 10)
    before = set(DATA.iterdir())
    response = client.post('/api/reports/context', files={'file': ('report.pdf', b'0'*11)})
    assert response.status_code == 413
    assert set(DATA.iterdir()) == before
