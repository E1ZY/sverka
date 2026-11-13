import sys

from PIL import Image

from app import ocr


def test_cli_numeric_ocr_preserves_grouped_amounts_and_confidence(monkeypatch):
    import pytesseract

    # Docker uses the CLI fallback, even when the developer has tesserocr.
    monkeypatch.setitem(sys.modules, 'tesserocr', None)
    calls = []

    def image_to_data(image, **kwargs):
        calls.append(kwargs)
        return {
            'text': ['', '5', '558', '474,83'],
            'conf': [-1, 83, 88, 96],
            'left': [0, 10, 20, 40], 'top': [0, 5, 5, 5],
            'width': [0, 8, 18, 35], 'height': [0, 10, 10, 10],
            'block_num': [0, 1, 1, 1], 'par_num': [0, 1, 1, 1],
            'line_num': [0, 1, 1, 1],
        }

    monkeypatch.setattr(pytesseract, 'image_to_data', image_to_data)
    result = ocr.words(Image.new('RGB', (100, 30), 'white'), psm=7, numeric=True)

    assert calls == [{'lang': 'eng', 'config': '--psm 7',
                      'output_type': pytesseract.Output.DICT, 'timeout': 90}]
    assert ' '.join(word['text'] for word in result) == '5 558 474,83'
    assert [word['confidence'] for word in result] == [83, 88, 96]
    assert result[-1]['bbox'] == [40, 5, 75, 15]
