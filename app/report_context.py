"""Conservative suggestions for a new case; never infer dates from a contract date."""
import calendar
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import ImageOps

from . import ocr
from .extractors import CONTRACT, clusters, page_image
from .ocr_labels import stage_candidates

FIELDS = ('contract', 'stage', 'period_start', 'period_end')
DATE = r'(?:\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2})'
MONTH = (r'(?:январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йяе]|июн[ьяе]|'
         r'июл[ьяе]|август[ае]?|сентябр[ьяе]|октябр[ьяе]|ноябр[ьяе]|декабр[ьяе])')
MONTH_STEMS = ('январ', 'феврал', 'март', 'апрел', 'ма', 'июн', 'июл', 'август',
               'сентябр', 'октябр', 'ноябр', 'декабр')
PERIOD = re.compile(
    r'(?:\bпериод\b[^\d:\n]{0,70}?:?\s*|\bза\s+)'
    rf'(?:с\s+)?(?:'
    rf'(?P<start>{DATE})\s*(?:г\.?\s*)?(?:по|до|-)\s*(?P<end>{DATE})|'
    rf'(?P<first_month>{MONTH})(?:\s+(?P<first_year>20\d{{2}})(?:\s*г(?:ода|\.)?)?)?'
    rf'\s*(?:по|до|-)\s*(?P<last_month>{MONTH})\s+(?P<year>20\d{{2}})|'
    rf'(?P<month>{MONTH})\s+(?P<month_year>20\d{{2}}))\b', re.I,
)
CONTRACT_ID = r'[\w]+(?:\s*[/.-]\s*[\w]+)*'
CONTRACT_LABEL = r'\b(?:номер\s+)?(?:договор(?:а|у|ом)?|контракт(?:а|у|ом)?)\b'
CONTRACT_PATTERNS = (
    re.compile(rf'{CONTRACT_LABEL}\s*(?:№|номер|:|No\.?)?\s*[«"“]?\s*(?P<value>{CONTRACT_ID})', re.I),
    re.compile(rf'{CONTRACT_LABEL}\s+от\s+{DATE}\s*(?:г\.?\s*)?№\s*(?P<value>{CONTRACT_ID})', re.I),
)
STAGE_PATTERNS = (
    re.compile(r'\b(?P<value>\d{1,3})(?:-?й)?[ \t]*этап(?:а|у|ом|е)?\b', re.I),
    re.compile(r'\bэтап(?:а|у|ом|е)?[ \t]*(?:№|номер|:)?[ \t]*(?P<value>\d{1,3})\b', re.I),
)


def _date(value):
    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError('Не распознана дата')


def _month(value):
    return next(i for i, stem in enumerate(MONTH_STEMS, 1) if value.lower().startswith(stem))


def _normalize(text):
    return unicodedata.normalize('NFC', text).replace('\u00a0', ' ').translate(str.maketrans('–—−‑', '----'))


def context_from_fragments(fragments):
    """A distinct second candidate makes a field ambiguous, even with lower OCR confidence."""
    parts, spans = [], []
    offset = 0
    for fragment in fragments:
        part = _normalize(fragment['text'])
        parts.append(part)
        if fragment.get('words'):
            spans.extend((offset + start, offset + end, confidence)
                         for start, end, confidence in fragment['words'])
        else:
            spans.append((offset, offset + len(part), fragment.get('confidence', 100)))
        offset += len(part) + 1
    text = '\n'.join(parts)
    candidates = {field: {} for field in FIELDS}

    def add(field, value, span):
        confidence = min((c for start, end, c in spans if start < span[1] and end > span[0]), default=0)
        candidates[field][value] = candidates[field].get(value, False) or confidence >= 80

    for pattern in CONTRACT_PATTERNS:
        for match in pattern.finditer(text):
            value = re.sub(r'\s+', '', match['value']).rstrip('.')
            if len(value) <= 80 and re.search(r'\d', value) and not re.fullmatch(DATE, value):
                add('contract', value, match.span('value'))
    for match in CONTRACT.finditer(text):
        add('contract', re.sub(r'\s+', '', match[0]), match.span())
    for pattern in STAGE_PATTERNS:
        for match in pattern.finditer(text):
            value = int(match['value'])
            if 1 <= value <= 100:
                add('stage', value, match.span('value'))
    for value, span in stage_candidates(text):
        add('stage', value, span)

    for match in PERIOD.finditer(text):
        try:
            if match['start']:
                start, end = _date(match['start']), _date(match['end'])
            elif match['first_month']:
                year = int(match['year'])
                start = date(int(match['first_year'] or year), _month(match['first_month']), 1)
                last = _month(match['last_month'])
                end = date(year, last, calendar.monthrange(year, last)[1])
            else:
                year, month = int(match['month_year']), _month(match['month'])
                start = date(year, month, 1)
                end = date(year, month, calendar.monthrange(year, month)[1])
            if start <= end and start.year == end.year:
                add('period_start', start.isoformat(), match.span())
                add('period_end', end.isoformat(), match.span())
        except ValueError:
            continue
    for field, label in (
        ('period_start', r'начало'), ('period_end', r'(?:конец|окончание)'),
    ):
        pattern = rf'\b{label}\s+(?:отч[её]тного\s+)?периода\s*:?\s*(?P<value>{DATE})\b'
        for match in re.finditer(pattern, text, re.I):
            try:
                add(field, _date(match['value']).isoformat(), match.span('value'))
            except ValueError:
                continue

    result = {}
    for field, values in candidates.items():
        value = next(iter(values), None)
        status = ('missing' if not values else 'ambiguous' if len(values) > 1 else
                  'found' if values[value] else 'uncertain')
        result[field] = {'value': value if status == 'found' else None, 'status': status}
    # Do not suggest a period the case API would reject.
    start, end = result['period_start']['value'], result['period_end']['value']
    if start and end and (start > end or start[:4] != end[:4]):
        for field in ('period_start', 'period_end'):
            result[field] = {'value': None, 'status': 'ambiguous'}
    return {'fields': result}


def _ocr_fragments(image, psm=6):
    lines = {}
    for token in ocr.words(image, psm=psm):
        lines.setdefault(token['line'], []).append(token)
    fragments = []
    for tokens in lines.values():
        parts, words = [], []
        offset = 0
        for token in tokens:
            text = _normalize(token['text'])
            parts.append(text)
            words.append((offset, offset + len(text), token['confidence']))
            offset += len(text) + 1
        fragments.append({'text': ' '.join(parts), 'words': words})
    return fragments


def _scan_fragments(image):
    """Read the KФЗ header and row labels separately from the dense money grid."""
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((1, max(30, w//25)), np.uint8))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((max(25, h//25), 1), np.uint8))
    ys = clusters(np.where((horizontal > 0).sum(axis=1) > w * .65)[0])
    xs = clusters(np.where((vertical > 0).sum(axis=0) > h * .08)[0])
    if len(xs) != 18 or len(ys) < 5:
        return _ocr_fragments(image)
    fragments = _ocr_fragments(image.crop((0, 0, w, ys[0])))
    for y0, y1 in zip(ys, ys[1:]):
        if not 8 < y1-y0 < h * .055:
            continue
        label = image.crop((xs[0]+2, y0+1, xs[2]-2, y1-1))
        label = ImageOps.expand(label.resize((label.width*5, label.height*5)), border=15, fill='white')
        fragments.extend(_ocr_fragments(label, psm=7))
    if ys[-1] < h - 1:
        fragments.extend(_ocr_fragments(image.crop((0, ys[-1], w, h))))
    return fragments


def extract_report_context(path):
    fragments = []
    if Path(path).suffix.lower() == '.pdf':
        with pymupdf.open(path) as doc:
            if not 1 <= len(doc) <= 50:
                raise ValueError('Для распознавания поддерживается от 1 до 50 страниц PDF')
            for i, page in enumerate(doc):
                text = page.get_text(sort=True)
                if len(text.strip()) >= 30:
                    fragments.append({'text': text, 'confidence': 100})
                else:
                    fragments.extend(_scan_fragments(page_image(path, i+1, dpi=300)))
    else:
        fragments = _scan_fragments(page_image(path, dpi=200))
    return context_from_fragments(fragments)
