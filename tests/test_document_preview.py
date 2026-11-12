import io

import pytest
from PIL import Image

from app.config import ROOT


@pytest.fixture
def preview_url(client):
    case = client.post('/api/cases', json={
        'title': 'Preview resolution', 'contract': '26/01/01-77', 'stage': 3,
        'period_start': '2026-01-01', 'period_end': '2026-01-31',
    }).json()
    with (ROOT/'cases/generated/00_clean/input/report.pdf').open('rb') as report:
        response = client.post(f'/api/cases/{case["id"]}/documents', data={'role': 'report'},
                               files=[('files', ('report.pdf', report, 'application/pdf'))])
    assert response.status_code == 201
    document = response.json()[0]
    return f'/api/cases/{case["id"]}/documents/{document["id"]}/page/1'


def test_high_resolution_preview_preserves_page_and_increases_detail(client, preview_url):
    default = client.get(preview_url)
    sharp = client.get(preview_url, params={'dpi': 300})
    assert default.status_code == sharp.status_code == 200
    assert sharp.headers['content-type'] == 'image/png'
    with Image.open(io.BytesIO(default.content)) as normal, Image.open(io.BytesIO(sharp.content)) as large:
        assert abs(large.width - normal.width * 300 / 180) <= 2
        assert abs(large.height - normal.height * 300 / 180) <= 2


@pytest.mark.parametrize('dpi', [0, 71, 361, 'invalid'])
def test_preview_rejects_invalid_or_excessive_resolution(client, preview_url, dpi):
    assert client.get(preview_url, params={'dpi': dpi}).status_code == 422
