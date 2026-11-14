"""Check the report's OCR workload and evidence against the real KФЗ scan."""
from pathlib import Path

import pytest

from app import extractors, ocr

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = {'contract': '24/03/15-01', 'stage': 3, 'period_start': '2026-01-01',
           'period_end': '2026-05-31', 'row_label': '3 этап, 2026 г.'}


@pytest.mark.parametrize('first_reading', ['confident', 'uncertain', 'invalid'])
def test_model_readings_skip_reference_rows_and_retry_only_when_needed(monkeypatch, first_reading):
    monkeypatch.setenv('OCR_PROVIDER', 'xiaomi')
    calls, progress = [], []
    def recognize(image, psm=6, numeric=False):
        calls.append((psm, numeric))
        if numeric and sum(is_numeric for _, is_numeric in calls) == 1:
            if first_reading == 'uncertain':
                # Mean confidence is 84%, but a single uncertain digit must trigger a retry.
                return [{'text': text, 'confidence': 20. if index == 0 else 100.}
                        for index, text in enumerate(['9', '0', '0', ',', '00'])]
            if first_reading == 'invalid':
                return [{'text': 'неразборчиво', 'confidence': 99.}]
        if numeric and first_reading != 'confident' and sum(is_numeric for _, is_numeric in calls) == 2:
            # Simulate a successful second model reading of the first amount.
            return [{'text': '5 558 474,83', 'confidence': 99.}]
        # A deterministic local recognizer stands in for costly GPU generation.
        return [{**token, 'confidence': 99.} for token in ocr._tesseract_words(image, psm, numeric)]
    monkeypatch.setattr(ocr, 'words', recognize)
    report = extractors.extract_report(next((ROOT/'task/data').glob('01_*.pdf')), CONTEXT,
                                       progress=lambda text, fraction: progress.append((text, fraction)))
    assert report['report_values'] == {'0200': '5558474.83', '0300': '1671359.96', '0800': '1145798.10',
                                       '0900': '3204744.51', 'total': '11580377.40'}
    assert report['needs_review'] is False
    assert report['contract'] == CONTEXT['contract']
    assert {(row['stage'], row['year']) for row in report['cost_rows']} == {(3, 2025), (3, 2026)}
    # 18 detail cells + 3 aggregate columns, with a bounded retry for empty cells.
    assert sum(numeric for _, numeric in calls) <= 25
    assert calls.count((6, False)) == 1  # header and business metadata share a reading
    fractions = [fraction for _, fraction in progress]
    assert fractions == sorted(fractions) and fractions[-1] == 1
    assert any('2025' in message for message, _ in progress)
    assert any('2026' in message for message, _ in progress)
    assert all(0 <= coordinate <= 1 for evidence in report['report_evidence'].values() for coordinate in evidence['bbox'])
