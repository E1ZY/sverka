"""Prepare pinned Xiaomi weights, verify local inference, then select the provider."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.ocr_settings import MODEL_ID, MODEL_REVISION, OCRSettings

MODEL_FILES = ('config.json', 'model.safetensors', 'processor_config.json',
               'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja')


def prepared_model(model_dir):
    try:
        manifest = json.loads((model_dir/'sverka-model.json').read_text(encoding='utf-8'))
        return (manifest.get('model') == MODEL_ID and manifest.get('revision') == MODEL_REVISION
                and all((model_dir/name).is_file() and (model_dir/name).stat().st_size > 0 for name in MODEL_FILES))
    except (OSError, ValueError):
        return False


def save_provider(path, values):
    lines = path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    lines = [line for line in lines if line.partition('=')[0].strip() not in values]
    content = '\n'.join([*lines, *(f'{key}={value}' for key, value in values.items()), ''])
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        if os.name == 'posix':
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def smoke_image():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (700, 100), 'white')
    fonts = ['C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font = next((ImageFont.truetype(path, 36) for path in fonts if Path(path).is_file()), ImageFont.load_default(size=36))
    ImageDraw.Draw(image).text((20, 25), 'TOTAL 1 234,56', font=font, fill='black')
    return image


def main(argv=None):
    parser = argparse.ArgumentParser(description='Скачать и включить локальный Xiaomi-OCR-0.')
    parser.add_argument('--device', choices=['auto', 'cuda', 'cpu', 'mps'], default='auto')
    parser.add_argument('--model-dir', type=Path, default=ROOT / '.runtime/models/xiaomi-ocr-0')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--download-only', action='store_true', help='Только подготовить веса; не запускать модель и не менять .env.')
    parser.add_argument('--if-missing', action='store_true', help='С --download-only: сохранить уже подготовленную закреплённую версию без сетевого запроса.')
    parser.add_argument('--disable', action='store_true', help='Вернуть Tesseract, сохранив веса Xiaomi.')
    args = parser.parse_args(argv)
    if args.if_missing and not args.download_only:
        parser.error('--if-missing используется только с --download-only.')
    model_dir = args.model_dir.resolve()
    if args.if_missing and prepared_model(model_dir):
        print(f'Xiaomi-OCR-0 уже подготовлена: {model_dir}. Повторное скачивание не требуется.', flush=True)
        return
    if args.disable:
        save_provider(args.env_file.resolve(), {'OCR_PROVIDER': 'tesseract'})
        print('Выбран Tesseract. Перезапустите приложение.')
        return
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        parser.error('Сначала установите requirements-xiaomi-ocr.txt по README.')
    print(f'Подготовка {MODEL_ID}, revision {MODEL_REVISION}. Веса: {model_dir}', flush=True)
    snapshot_download(repo_id=MODEL_ID, revision=MODEL_REVISION, local_dir=model_dir,
                      allow_patterns=['*.json', '*.safetensors', '*.jinja', '*.txt', '*.model'])
    (model_dir / 'sverka-model.json').write_text(json.dumps({'model': MODEL_ID, 'revision': MODEL_REVISION}), encoding='utf-8')
    if args.download_only:
        print('Веса подготовлены. Режим приложения не изменён.')
        return
    from app.xiaomi_ocr import words
    settings = OCRSettings(provider='xiaomi', model=str(model_dir), device=args.device)
    image = smoke_image()
    tokens = words(image, settings, psm=7)
    text = ' '.join(token['text'] for token in tokens)
    if '1234.56' not in re.sub(r'\s', '', text).replace(',', '.'):
        raise RuntimeError(f'Проверочная сумма не распознана: {text!r}. Режим приложения не изменён.')
    report = {'model': MODEL_ID, 'revision': MODEL_REVISION, 'device': args.device, 'text': text,
              'minimum_confidence': min(token['confidence'] for token in tokens)}
    (ROOT / '.runtime').mkdir(exist_ok=True)
    (ROOT / '.runtime/xiaomi-smoke-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    image.save(ROOT / '.runtime/xiaomi-smoke.png')
    try:
        configured_path = model_dir.relative_to(ROOT).as_posix()
    except ValueError:
        configured_path = model_dir.as_posix()
    save_provider(args.env_file.resolve(), {'OCR_PROVIDER': 'xiaomi', 'XIAOMI_OCR_MODEL': configured_path,
                                           'XIAOMI_OCR_DEVICE': args.device})
    print(f'Проверка пройдена: {text}. Xiaomi-OCR-0 включена; перезапустите приложение.', flush=True)


if __name__ == '__main__':
    main()
