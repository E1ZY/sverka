"""Download public OCR language weights. Never sends or uploads user documents."""
import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
MODELS = {
    'eng': '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',
    'rus': 'e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225',
}


def main():
    target = Path(os.getenv('TESSDATA_PREFIX', ROOT/'.runtime'/'tessdata'))
    target.mkdir(parents=True, exist_ok=True)
    for lang, expected in MODELS.items():
        path = target/f'{lang}.traineddata'
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            print(f'{lang}: already installed')
            continue
        with urlopen(f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{lang}.traineddata', timeout=60) as response:
            data = response.read(30*1024*1024)
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f'{lang}: model checksum changed; verify the model before updating the pinned checksum')
        path.write_bytes(data)
        print(f'{lang}: installed')


if __name__ == '__main__':
    main()
