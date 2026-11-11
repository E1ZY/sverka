"""Local OCR provider. No network calls. Coordinates are in input-image pixels."""
import os
from pathlib import Path

from PIL import Image

from .config import ROOT


def words(image: Image.Image, psm=6, numeric=False):
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
    config = f'--psm {psm}' + (' -c tessedit_char_whitelist=0123456789.,-' if numeric else '')
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT, timeout=90)
    return [{'text': t, 'bbox': [data['left'][i], data['top'][i], data['left'][i] + data['width'][i], data['top'][i] + data['height'][i]],
             'confidence': float(data['conf'][i]), 'line': f"{data['block_num'][i]}.{data['par_num'][i]}.{data['line_num'][i]}"}
            for i, t in enumerate(data['text']) if t.strip()]


def text(image, psm=6, numeric=False):
    return ' '.join(w['text'] for w in words(image, psm, numeric))
