"""Explicit OCR configuration; model weights are prepared separately, never downloaded at runtime."""
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT

MODEL_ID = 'xiaomi-research/Xiaomi-OCR-0'
MODEL_REVISION = 'bbd8cf8d21f256b3644b44cb860f3a7cecb93c30'
KEYS = {'OCR_PROVIDER', 'XIAOMI_OCR_MODEL', 'XIAOMI_OCR_DEVICE', 'XIAOMI_OCR_MAX_NEW_TOKENS', 'XIAOMI_OCR_TIMEOUT'}


@dataclass(frozen=True)
class OCRSettings:
    provider: str = 'tesseract'
    model: str = str(ROOT / '.runtime' / 'models' / 'xiaomi-ocr-0')
    device: str = 'auto'
    max_new_tokens: int = 4096
    timeout: float = 180

    def __post_init__(self):
        if self.provider not in {'tesseract', 'xiaomi'}:
            raise ValueError('OCR_PROVIDER должен быть tesseract или xiaomi.')
        if self.device not in {'auto', 'cpu', 'cuda', 'mps'}:
            raise ValueError('XIAOMI_OCR_DEVICE: auto, cpu, cuda или mps.')
        if not 32 <= self.max_new_tokens <= 8192 or not 1 <= self.timeout <= 1800:
            raise ValueError('XIAOMI_OCR_MAX_NEW_TOKENS: 32–8192; XIAOMI_OCR_TIMEOUT: 1–1800 секунд.')

    @classmethod
    def from_env(cls, path=None):
        values = {}
        path = Path(path) if path is not None else ROOT / '.env'
        if path.is_file():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                key, sep, value = line.partition('=')
                if sep and key.strip() in KEYS:
                    values[key.strip()] = value.strip().strip('\"\'')
        values.update({key: os.environ[key] for key in KEYS if key in os.environ})
        model = Path(values.get('XIAOMI_OCR_MODEL', cls.model)).expanduser()
        if not model.is_absolute():
            model = ROOT / model
        return cls(values.get('OCR_PROVIDER', 'tesseract'), str(model.resolve()),
                   values.get('XIAOMI_OCR_DEVICE', 'auto'),
                   int(values.get('XIAOMI_OCR_MAX_NEW_TOKENS', 4096)), float(values.get('XIAOMI_OCR_TIMEOUT', 180)))

    def signature(self):
        if self.provider == 'tesseract':
            return 'tesseract-v1'
        manifest = Path(self.model) / 'sverka-model.json'
        revision = manifest.read_text(encoding='utf-8') if manifest.is_file() else 'unprepared'
        config = json.dumps([self.model, revision, self.device, self.max_new_tokens, self.timeout])
        return 'xiaomi-v1-' + hashlib.sha256(config.encode()).hexdigest()[:16]
