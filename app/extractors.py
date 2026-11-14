import calendar
import hashlib
import io
import re
from functools import lru_cache
from datetime import date
from decimal import Decimal
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from docx import Document as WordDocument
from openpyxl import load_workbook
from PIL import Image, ImageOps

from . import ocr
from .card_metadata import card_metadata
from .domain import RULES, classify, money
from .ocr_labels import stage_candidates
from .ocr_settings import OCRSettings

SUPPORTED = {'.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg'}
REPORT_PARSER_VERSION = 'kfz-grid-v5-progress'
MONTHS = ['январ', 'феврал', 'март', 'апрел', 'ма', 'июн', 'июл', 'август', 'сентябр', 'октябр', 'ноябр', 'декабр']
CONTRACT = re.compile(r'\b\d{2}\s*/\s*\d{2}\s*/\s*\d{2}\s*[-–—]\s*\d{2}\b')
AMOUNT = re.compile(r'(?<![\d/])[-−]?(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)[,.]\d{2}(?!\d)')


def fragment(text, **locator):
    return {'text': text, **locator}


def page_image(path, page=1, dpi=180):
    if Path(path).suffix.lower() == '.pdf':
        with pymupdf.open(path) as doc:
            if not 1 <= page <= len(doc):
                raise ValueError('Нет такой страницы')
            pix = doc[page - 1].get_pixmap(dpi=dpi, alpha=False)
            return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    if page != 1:
        raise ValueError('У изображения одна страница')
    return ImageOps.exif_transpose(Image.open(path)).convert('RGB')


def image_fragments(image, page):
    tokens = ocr.words(image)
    lines = {}
    for token in tokens:
        lines.setdefault(token['line'], []).append(token)
    w, h = image.size
    result = []
    for line in lines.values():
        box = [min(t['bbox'][0] for t in line), min(t['bbox'][1] for t in line), max(t['bbox'][2] for t in line), max(t['bbox'][3] for t in line)]
        result.append(fragment(' '.join(t['text'] for t in line), page=page,
                               bbox=[box[0] / w, box[1] / h, box[2] / w, box[3] / h],
                               confidence=round(sum(t['confidence'] for t in line) / len(line), 1),
                               ocr_provider=line[0].get('provider', 'tesseract'),
                               confidence_basis=line[0].get('confidence_basis', 'ocr'),
                               bbox_precision='region' if any(t.get('bbox_precision') == 'region' for t in line) else 'word'))
    return result


def read_fragments(path):
    ext = Path(path).suffix.lower()
    if ext == '.docx':
        doc = WordDocument(path)
        result = [fragment(p.text, paragraph=i + 1) for i, p in enumerate(doc.paragraphs) if p.text.strip()]
        for ti, table in enumerate(doc.tables, 1):
            for ri, row in enumerate(table.rows, 1):
                for ci, cell in enumerate(row.cells, 1):
                    if cell.text.strip():
                        result.append(fragment(cell.text, table=ti, row=ri, column=ci))
        return result
    if ext == '.pdf':
        result = []
        with pymupdf.open(path) as doc:
            if len(doc) > 50:
                raise ValueError('MVP поддерживает не более 50 страниц в одном PDF')
            for i, page in enumerate(doc):
                blocks = page.get_text('blocks')
                blocks = [b for b in blocks if len(b) > 6 and b[6] == 0 and b[4].strip()]
                if sum(len(b[4]) for b in blocks) >= 30:
                    for b in blocks:
                        result.append(fragment(b[4].strip(), page=i + 1, bbox=[b[0]/page.rect.width, b[1]/page.rect.height, b[2]/page.rect.width, b[3]/page.rect.height], confidence=100))
                else:
                    result.extend(image_fragments(page_image(path, i + 1), i + 1))
        return result
    if ext in {'.png', '.jpg', '.jpeg'}:
        return image_fragments(page_image(path), 1)
    raise ValueError('Неподдерживаемый формат')


def metadata(fragments):
    text = '\n'.join(f['text'] for f in fragments)
    contract = CONTRACT.search(text)
    dt = re.search(r'\b(\d{2})[.](\d{2})[.](20\d{2})\b', text)
    document_date = None
    if dt:
        document_date = date(int(dt[3]), int(dt[2]), int(dt[1])).isoformat()
    number = re.search(r'(?:№|документ\s*:)\s*([\w/-]+)', text, re.I)
    if number is None:
        number = re.search(r'(?:служебная записка|справка о расходах|универсальный передаточный документ)\s+([^\n]+)', text, re.I)
    period_start = period_end = document_date
    lower = text.lower()
    month = re.search(r'(?:период\s*:?|за)\s*([а-яё]+)\s+(20\d{2})', lower)
    if month:
        mi = next((i for i, stem in enumerate(MONTHS, 1) if month[1].startswith(stem)), None)
        if mi:
            year = int(month[2])
            period_start = date(year, mi, 1).isoformat()
            period_end = date(year, mi, calendar.monthrange(year, mi)[1]).isoformat()
    counterparty = re.search(r'(?:исполнитель|поставщик)\s*:?\s*([^\n]+)', text, re.I)
    return {'contract': re.sub(r'\s', '', contract[0]).replace('–', '-').replace('—', '-') if contract else None,
            'number': number[1] if number else None, 'document_date': document_date,
            'period_start': period_start, 'period_end': period_end,
            'counterparty': counterparty[1].strip() if counterparty else '', 'text': text, 'business_metadata': card_metadata(fragments)}


def extract_primary(path):
    if Path(path).suffix.lower() == '.xlsx':
        return extract_xlsx(path)
    fragments = read_fragments(path)
    data = metadata(fragments)
    candidates = []
    for f in fragments:
        for match in AMOUNT.finditer(f['text'].replace('−', '-')):
            # A date has two two-digit fractions, but no monetary meaning.
            if re.search(r'\d{2}\.\d{2}\.\d{4}', f['text']) and not re.search(r'руб|стоим|сумм|итого|оплат', f['text'], re.I):
                continue
            score = 4 if re.search(r'итого|к оплате|сумма|стоимость', f['text'], re.I) else 1
            candidates.append((score, money(match[0]), f))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0]
        top_amounts = {a for score, a, f in candidates if score == best[0]}
        data.update(amount=str(best[1]), amount_evidence=best[2], needs_review=len(top_amounts) != 1 or best[2].get('confidence', 100) < 65)
    else:
        data.update(amount=None, amount_evidence=None, needs_review=True)
    data['article'] = classify(data['text'])
    data['classification_evidence'] = next((f for f in fragments if classify(f['text']) == data['article']), None)
    data['fragments'] = fragments
    data['parser'] = 'text-or-local-ocr-v1'
    return data


def extract_xlsx(path):
    book = load_workbook(path, data_only=False, read_only=True)
    fragments = []
    rows = []
    for sheet in book:
        # OOXML permits worksheets without a stored <dimension>. Read-only
        # openpyxl reports None until the used range is calculated explicitly.
        if sheet.max_row is None or sheet.max_column is None:
            sheet.calculate_dimension(force=True)
        if sheet.max_row > 10000 or sheet.max_column > 100:
            raise ValueError('Слишком большая таблица для MVP')
        for row in sheet:
            cells = [c for c in row if c.value is not None]
            if cells:
                rows.append((sheet.title, cells))
                fragments.extend(fragment(str(c.value), sheet=sheet.title, range=c.coordinate) for c in cells)
    data = metadata(fragments)
    terms, article = [], None
    for sheet, cells in rows:
        codes = [str(c.value).zfill(4) for c in cells if str(c.value) in {'0201', '0202', '201', '202', '0300', '300'}]
        if not codes:
            continue
        code = codes[0]
        if code in {'0201', '0202'}:
            amount_cell = next((c for c in cells if isinstance(c.value, (float, int)) and c.column == 3), None)
            article = '0200'
        else:
            amount_cell = next((c for c in cells if isinstance(c.value, (float, int)) and c.column == 2), None)
            article = '0300'
        if amount_cell:
            terms.append({'amount': str(money(amount_cell.value)), 'evidence': fragment(str(amount_cell.value), sheet=sheet, range=amount_cell.coordinate)})
    if not terms:
        raise ValueError('Не распознана поддерживаемая структура ведомости или расчёта взносов')
    amount = sum((money(t['amount']) for t in terms), Decimal(0))
    ranges = [t['evidence']['range'] for t in terms]
    evidence = fragment(' + '.join(t['amount'] for t in terms), sheet=terms[0]['evidence']['sheet'], range=':'.join([ranges[0], ranges[-1]]) if len(ranges) > 1 else ranges[0])
    data.update(article=article, amount=str(amount), amount_evidence=evidence, classification_evidence=evidence,
                calculation=terms, fragments=fragments, needs_review=False, parser='xlsx-register-v1')
    book.close()
    return data


def clusters(indices):
    groups = []
    for i in indices:
        if not groups or i - groups[-1][-1] > 2:
            groups.append([int(i)])
        else:
            groups[-1].append(int(i))
    return [int(sum(g)/len(g)) for g in groups]


def pdf_region_text(path, box):
    """Read native PDF glyphs in a normalized page box before resorting to OCR."""
    if Path(path).suffix.lower() != '.pdf':
        return ''
    with pymupdf.open(path) as doc:
        page = doc[0]
        rect = pymupdf.Rect(box[0]*page.rect.width, box[1]*page.rect.height,
                            box[2]*page.rect.width, box[3]*page.rect.height)
        return page.get_textbox(rect).strip()


def extract_report(path, context, progress=None):
    """KФЗ profile: detect table grid, choose row by OCR label, then read configured columns.

    No fixed image coordinates or amounts; transformed/renamed scans use the same profile.
    """
    update = progress or (lambda message, fraction: None)
    use_xiaomi = OCRSettings.from_env().provider == 'xiaomi'
    update('КФЗ: подготовка изображения и поиск таблицы', .01)
    image = page_image(path, 1, dpi=200)
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((1, max(30, w//25)), np.uint8))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((max(25, h//25), 1), np.uint8))
    ys = clusters(np.where((horizontal > 0).sum(axis=1) > w * .65)[0])
    xs = clusters(np.where((vertical > 0).sum(axis=0) > h * .08)[0])
    if len(xs) != 18 or len(ys) < 5:
        raise ValueError(f'Не распознана сетка формы КФЗ: {len(xs)-1} колонок. Требуется профиль формы или более чёткий скан.')
    clean = Image.fromarray(255 - cv2.subtract(bw, cv2.bitwise_or(horizontal, vertical)))
    row = None
    labels = []
    recognized_rows = []
    year = str(date.fromisoformat(context['period_start']).year)
    label_rows = [(y0, y1) for y0, y1 in zip(ys, ys[1:]) if 8 < y1-y0 < h * .055]
    for index, (y0, y1) in enumerate(label_rows):
        update(f'КФЗ: поиск этапа и года · строка {index+1}/{len(label_rows)}', .03 + .12*index/max(1,len(label_rows)))
        label_image = image.crop((xs[0]+2, y0+1, xs[2]-2, y1-1))
        label_image = ImageOps.expand(label_image.resize((label_image.width*5, label_image.height*5), Image.Resampling.LANCZOS), border=15, fill='white')
        label = ocr.text(label_image, psm=7)
        labels.append(label)
        stages = {value for value, _ in stage_candidates(label)}
        if len(stages) > 1:
            raise ValueError('Неоднозначный этап в строке КФЗ: ' + label)
        detected_stage = next(iter(stages), None)
        year_match = re.search(r'20\d{2}', label)
        if detected_stage is not None:
            recognized_rows.append({'stage': detected_stage, 'year': int(year_match[0]) if year_match else None, 'bounds': (y0, y1)})
        if year_match and year_match[0] == year and detected_stage == context['stage']:
            if row is not None:
                raise ValueError('Найдено несколько строк с выбранными этапом и годом')
            row = (y0, y1)
    if row is None:
        raise ValueError('Не найдена строка этапа и года: ' + ' | '.join(labels))
    values, evidence, confidences = {}, {}, []
    y0, y1 = row
    @lru_cache(maxsize=128)
    def read_cell(column, y0, y1):
        x0, x1 = xs[column-1], xs[column]
        candidates = []
        native_text = pdf_region_text(path, [x0/w, y0/h, x1/w, y1/h])
        normalized = re.sub(r'\s', '', native_text).replace('.', ',')
        if re.fullmatch(r'-?\d+,\d{2}', normalized):
            candidates.append((100, str(money(normalized)), native_text))
        for inset in (() if candidates else (1, 2)):
            crop = image.crop((x0+2, y0+inset, x1-2, y1-inset))
            crop = ImageOps.expand(crop.resize((crop.width*5, crop.height*5), Image.Resampling.LANCZOS), border=20, fill='white')
            tokens = ocr.words(crop, psm=7, numeric=True)
            text = ' '.join(t['text'] for t in tokens)
            normalized = text.replace(' ', '').replace('.', ',')
            confidence = sum(t['confidence'] for t in tokens)/len(tokens) if tokens else 0
            if re.fullmatch(r'\d+,\d{2}', normalized):
                candidates.append((confidence, str(money(normalized)), text))
                if use_xiaomi and tokens and min(token['confidence'] for token in tokens) >= 80:
                    break  # Retry the second crop only when the first model reading is uncertain.
        confidence, value, text = max(candidates, default=(0, None, ''), key=lambda c: c[0])
        return value, fragment(text, page=1, bbox=[x0/w, y0/h, x1/w, y1/h], confidence=round(confidence, 1), column=column), confidence
    for code, column in RULES['report_columns'].items():
        update(f'КФЗ: чтение итогов · статья {code}', .15 + .15*len(values)/len(RULES['report_columns']))
        values[code], evidence[code], confidence = read_cell(column, *row)
        confidences.append(confidence)
    cost_rows = []
    # Only annual rows of the selected stage feed the cost tree. Previous stages
    # and an already aggregated total row do not require separate model calls.
    detail_rows = [recognized for recognized in recognized_rows
                   if recognized['stage'] == context['stage'] and recognized['year'] is not None]
    detail_columns = (4, 7, 8, 9, 12, 13, 14, 15, 16)
    for index, recognized in enumerate(detail_rows):
        detail_values, detail_evidence = {}, {}
        for column_index, column in enumerate(detail_columns):
            completed = index*len(detail_columns)+column_index
            update(f'КФЗ: {recognized["year"]} год · ячейка {completed+1}/{len(detail_rows)*len(detail_columns)}',
                   .30 + .50*completed/max(1,len(detail_rows)*len(detail_columns)))
            value, locator, confidence = read_cell(column, *recognized['bounds'])
            detail_values[str(column)] = value if confidence >= 45 else None
            detail_evidence[str(column)] = locator
        cost_rows.append({'stage': recognized['stage'], 'year': recognized['year'], 'values': detail_values, 'evidence': detail_evidence})
    # Header OCR separately avoids dense grid text corrupting contract identifiers.
    header = image.crop((0, 0, w, ys[0]))
    native_header = pdf_region_text(path, [0, 0, 1, ys[0]/h])
    update('КФЗ: чтение реквизитов карточки', .82)
    header_image = header.resize((header.width*2, header.height*2), Image.Resampling.LANCZOS) if use_xiaomi else header
    header_fragments = [fragment(native_header, page=1, bbox=[0,0,1,ys[0]/h], confidence=100)] if native_header else image_fragments(header_image, 1)
    if not native_header:
        for item in header_fragments:
            item['bbox'][1] *= ys[0]/h
            item['bbox'][3] *= ys[0]/h
    data = metadata(header_fragments)
    if not native_header and not use_xiaomi:
        business_fragments = image_fragments(header.resize((header.width*2, header.height*2), Image.Resampling.LANCZOS), 1)
        for item in business_fragments:
            item['bbox'][1] *= ys[0]/h
            item['bbox'][3] *= ys[0]/h
        detailed = card_metadata(business_fragments)
        for key, item in detailed.items():
            if item['status'] == 'missing' and data['business_metadata'][key]['value']:
                detailed[key] = {**data['business_metadata'][key], 'status': 'uncertain'}
        data['business_metadata'] = detailed
    data.update(report_values=values, report_evidence=evidence, cost_rows=cost_rows, row_label=context['row_label'],
                needs_review=any(v is None for v in values.values()) or min(confidences) < 45,
                parser=REPORT_PARSER_VERSION, fragments=list(evidence.values()))
    update('КФЗ: распознавание завершено', 1.)
    return data


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
