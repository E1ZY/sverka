"""One-off Compose service: prepare shared weights before API/worker start."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.setup_xiaomi_ocr import main as setup_model
from scripts.setup_xiaomi_ocr import MODEL_FILES


def main():
    if os.getenv('OCR_PROVIDER', 'xiaomi') != 'xiaomi':
        print('Xiaomi OCR не выбрана; подготовка весов пропущена.', flush=True)
        return
    model_dir = Path(os.getenv('XIAOMI_OCR_MODEL', '/models/xiaomi-ocr-0'))
    setup_model(['--download-only', '--if-missing', '--model-dir', str(model_dir)])
    # A host umask of 077 must not make public model weights unreadable to UID 10001.
    for directory in (model_dir.parent, model_dir):
        directory.chmod(directory.stat().st_mode | 0o055)
    for name in (*MODEL_FILES, 'sverka-model.json'):
        path = model_dir/name
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o044)


if __name__ == '__main__':
    main()
