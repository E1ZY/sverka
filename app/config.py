import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('DATA_DIR', ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{(DATA / "audit.db").as_posix()}')
DEMO_DIR = Path(os.getenv('DEMO_DIR', ROOT / 'task' / 'данные'))
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CASE_FILES = 100
PIPELINE_VERSION = 'mvp-1.0'
