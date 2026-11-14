"""Selectable local OCR providers. Coordinates are in input-image pixels."""
from difflib import SequenceMatcher
import json
import os
from pathlib import Path

from PIL import Image

from .config import ROOT
from .ocr_settings import OCRSettings


def words(image: Image.Image, psm=6, numeric=False):
    settings = OCRSettings.from_env()
    if settings.provider == 'xiaomi':
        from .xiaomi_ocr import words as xiaomi_words
        result = xiaomi_words(image, settings, psm=psm, numeric=numeric)
        if psm == 7:
            # Callers already know the cell/label region and do not consume word boxes.
            return result
        # Tesseract supplies locations only; Xiaomi remains the text recognizer.
        # Unmatched text keeps its honest, coarse input-region box.
        try:
            layout = _tesseract_words(image, psm, numeric)
        except Exception:
            layout = []
        normalize = lambda token: token['text'].casefold().strip()
        for block in SequenceMatcher(None, list(map(normalize, result)), list(map(normalize, layout)), autojunk=False).get_matching_blocks():
            for offset in range(block.size):
                result[block.a+offset]['bbox'] = layout[block.b+offset]['bbox']
                result[block.a+offset]['bbox_precision'] = 'word'
        return result
    return _tesseract_words(image, psm, numeric)


def signature():
    return OCRSettings.from_env().signature()


def provenance():
    settings = OCRSettings.from_env()
    result = {'provider': settings.provider, 'signature': settings.signature()}
    if settings.provider == 'xiaomi':
        manifest = Path(settings.model) / 'sverka-model.json'
        metadata = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
        result.update(model=metadata.get('model', 'local'), revision=metadata.get('revision'), device=settings.device)
    return result


def _tesseract_words(image: Image.Image, psm=6, numeric=False):
    lang = 'eng' if numeric else 'rus+eng'
    try:
        import tesserocr
    except ImportError:
        tesserocr = None
    tessdata = Path(os.getenv('TESSDATA_PREFIX', ROOT / '.runtime' / 'tessdata'))
    if tesserocr is not None and tessdata.exists():
        result = []
        with tesserocr.PyTessBaseAPI(path=str(tessdata), lang=lang, psm=psm) as api:
            if numeric:
                api.SetVariable('tessedit_char_whitelist', '0123456789.,- ')
            api.SetImage(image.convert('RGB'))
            api.Recognize()
            it = api.GetIterator()
            line = 0
            if it:
                for token in tesserocr.iterate_level(it, tesserocr.RIL.WORD):
                    try:
                        text = token.GetUTF8Text(tesserocr.RIL.WORD)
                    except RuntimeError:
                        continue
                    if not text or not text.strip():
                        continue
                    if token.IsAtBeginningOf(tesserocr.RIL.TEXTLINE):
                        line += 1
                    result.append({'text': text.strip(), 'bbox': list(token.BoundingBox(tesserocr.RIL.WORD)),
                                   'confidence': round(token.Confidence(tesserocr.RIL.WORD), 1), 'line': line})
        return result
    import pytesseract
    if os.getenv('TESSERACT_CMD'):
        pytesseract.pytesseract.tesseract_cmd = os.environ['TESSERACT_CMD']
    # Grouped amounts contain spaces. A CLI allowlist without spaces merges
    # the groups and can return confidence 0 even for a correctly read amount.
    # The report parser validates the numeric format after recognition.
    config = f'--psm {psm}'
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT, timeout=90)
    return [{'text': t, 'bbox': [data['left'][i], data['top'][i], data['left'][i] + data['width'][i], data['top'][i] + data['height'][i]],
             'confidence': float(data['conf'][i]), 'line': f"{data['block_num'][i]}.{data['par_num'][i]}.{data['line_num'][i]}"}
            for i, t in enumerate(data['text']) if t.strip()]


def text(image, psm=6, numeric=False):
    return ' '.join(w['text'] for w in words(image, psm, numeric))
