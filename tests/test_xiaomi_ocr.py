import math
import sys
from types import SimpleNamespace
from contextlib import nullcontext

import pytest
from PIL import Image

from app import ocr, xiaomi_ocr
from app.ocr_settings import KEYS, OCRSettings
from app.ocr_labels import stage_candidates
from scripts import setup_xiaomi_ocr


@pytest.mark.parametrize('text', ['3 этап, 2026 г.', '3 tran, 2026 r.', '3 3ran, 2026 r.', '3 зtan, 2026 г.', '3 этaп, 2026'])
def test_mixed_script_stage_labels_keep_the_explicit_stage_and_year(text):
    assert list(stage_candidates(text)) == [(3, (0, 1))]


@pytest.mark.parametrize('text', ['3 акт, 2026', '2026 год', '3 train 2026', 'этап не указан', '101 этап'])
def test_stage_normalization_does_not_invent_a_stage_from_other_words(text):
    assert list(stage_candidates(text)) == []


class CharacterTokenizer:
    all_special_ids = [0]

    def decode(self, ids, **kwargs):
        return ''.join(chr(value) for value in ids if value)

    def __call__(self, text, **kwargs):
        return {'input_ids': list(map(ord, text)), 'offset_mapping': [(i, i+1) for i in range(len(text))]}


def test_generation_preserves_lines_and_uncertain_amount_not_whole_page_average():
    text = 'TOTAL 1234.56\nДоговор 24/03/15-01'
    ids = [*map(ord, text), 0]
    scores = [math.log(.98)] * len(ids)
    scores[6:13] = [math.log(.1)] * 7
    words = xiaomi_ocr.generation_words(CharacterTokenizer(), ids, scores, (700, 200))
    assert [word['text'] for word in words] == ['TOTAL', '1234.56', 'Договор', '24/03/15-01']
    assert [word['line'] for word in words] == [1, 1, 2, 2]
    assert words[0]['confidence'] == 98
    assert words[1]['confidence'] == 10
    assert all(word['bbox'] == [0, 0, 700, 200] and word['bbox_precision'] == 'region' for word in words)


def test_noncanonical_tokenization_uses_decoded_prefixes_without_raising_confidence():
    class NoOffsetsTokenizer(CharacterTokenizer):
        def __call__(self, *args, **kwargs):
            raise NotImplementedError()
    tokenizer = NoOffsetsTokenizer()
    tokens = xiaomi_ocr.generation_words(tokenizer, [ord('Я'), ord('0'), 0], [math.log(.3), math.log(.9), 0], (60, 20))
    assert tokens[0]['text'] == 'Я0'
    assert tokens[0]['confidence'] < 60


def test_xiaomi_uses_real_matching_boxes_and_keeps_unmatched_text_coarse(monkeypatch):
    monkeypatch.setattr(ocr.OCRSettings, 'from_env', lambda: OCRSettings(provider='xiaomi'))
    model_words = [{'text': 'Сумма', 'bbox': [0, 0, 200, 40], 'confidence': 91, 'line': 1, 'bbox_precision': 'region'},
                   {'text': '100,00', 'bbox': [0, 0, 200, 40], 'confidence': 52, 'line': 1, 'bbox_precision': 'region'}]
    monkeypatch.setattr(xiaomi_ocr, 'words', lambda *a, **k: model_words)
    monkeypatch.setattr(ocr, '_tesseract_words', lambda *a: [{'text': 'Сумма', 'bbox': [2, 4, 60, 25]}, {'text': '180,00', 'bbox': [65, 4, 150, 25]}])
    result = ocr.words(Image.new('RGB', (200, 40)))
    assert result[0]['bbox'] == [2, 4, 60, 25]
    assert result[0]['bbox_precision'] == 'word'
    assert result[1]['text'] == '100,00' and result[1]['confidence'] == 52
    assert result[1]['bbox'] == [0, 0, 200, 40] and result[1]['bbox_precision'] == 'region'


def test_xiaomi_does_not_silently_fall_back_to_tesseract(monkeypatch):
    monkeypatch.setattr(ocr.OCRSettings, 'from_env', lambda: OCRSettings(provider='xiaomi'))
    def fail(*args, **kwargs):
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(xiaomi_ocr, 'words', fail)
    with pytest.raises(RuntimeError, match='model unavailable'):
        ocr.words(Image.new('RGB', (50, 20)))


def test_known_cell_region_does_not_run_a_second_ocr_for_word_locations(monkeypatch):
    monkeypatch.setattr(ocr.OCRSettings, 'from_env', lambda: OCRSettings(provider='xiaomi'))
    result = [{'text': '100,00', 'bbox': [0, 0, 50, 20], 'confidence': 91, 'line': 1, 'bbox_precision': 'region'}]
    monkeypatch.setattr(xiaomi_ocr, 'words', lambda *a, **k: result)
    def unexpected(*args):
        raise AssertionError('A cell already has a known source rectangle')
    monkeypatch.setattr(ocr, '_tesseract_words', unexpected)
    assert ocr.words(Image.new('RGB', (50, 20)), psm=7, numeric=True) == result


def test_missing_model_has_actionable_setup_error(tmp_path):
    with pytest.raises(RuntimeError, match='setup_xiaomi_ocr.py'):
        xiaomi_ocr._load(str(tmp_path), 'cpu')


def test_truncated_model_output_is_rejected(monkeypatch):
    class Inputs(dict):
        def __init__(self):
            super().__init__(input_ids=SimpleNamespace(shape=(1, 5)))
        def to(self, device):
            return self
    class Output:
        def __getitem__(self, key):
            return SimpleNamespace(tolist=lambda: [ord('1')])
    model = SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=0), generate=lambda **k: Output())
    processor = SimpleNamespace(apply_chat_template=lambda *a, **k: Inputs())
    monkeypatch.setattr(xiaomi_ocr, '_load', lambda *a: (SimpleNamespace(inference_mode=nullcontext), processor, model, 'cpu'))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(LogitsProcessor=object))
    with pytest.raises(RuntimeError, match='Частичный результат не принят'):
        xiaomi_ocr.words(Image.new('RGB', (50, 20)), OCRSettings(provider='xiaomi'))


def test_settings_and_signature_track_provider_and_model_revision(tmp_path, monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / '.env'
    path.write_text(f'OCR_PROVIDER=xiaomi\nXIAOMI_OCR_DEVICE=cpu\nXIAOMI_OCR_MODEL={tmp_path.as_posix()}\n', encoding='utf-8')
    settings = OCRSettings.from_env(path)
    before = settings.signature()
    (tmp_path/'sverka-model.json').write_text('{"revision":"new"}', encoding='utf-8')
    assert before != settings.signature()
    monkeypatch.setenv('OCR_PROVIDER', 'tesseract')
    assert OCRSettings.from_env(path).signature() == 'tesseract-v1'
    monkeypatch.setenv('OCR_PROVIDER', 'invalid')
    with pytest.raises(ValueError, match='OCR_PROVIDER'):
        OCRSettings.from_env(path)


@pytest.mark.parametrize('success', [True, False])
def test_setup_enables_only_after_smoke_and_preserves_auth(tmp_path, monkeypatch, success):
    path = tmp_path / '.env'
    before = 'AUTH_MODE=password\nAUTH_PASSWORD_HASH=keep-this-hash\nPOSTGRES_PASSWORD=keep-db\nOCR_PROVIDER=tesseract\n'
    path.write_text(before, encoding='utf-8')
    monkeypatch.setattr(setup_xiaomi_ocr, 'ROOT', tmp_path)
    def download(**kwargs):
        kwargs['local_dir'].mkdir(exist_ok=True)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=download))
    monkeypatch.setattr(xiaomi_ocr, 'words', lambda *a, **k: [{'text': '1 234,56' if success else '900,00', 'confidence': 90}])
    args = ['--model-dir', str(tmp_path/'model'), '--env-file', str(path), '--device', 'cpu']
    if not success:
        with pytest.raises(RuntimeError, match='Проверочная сумма'):
            setup_xiaomi_ocr.main(args)
        assert path.read_text(encoding='utf-8') == before
    else:
        setup_xiaomi_ocr.main(args)
        after = path.read_text(encoding='utf-8')
        assert 'AUTH_PASSWORD_HASH=keep-this-hash\nPOSTGRES_PASSWORD=keep-db\n' in after
        assert after.count('OCR_PROVIDER=') == 1 and 'OCR_PROVIDER=xiaomi\n' in after
