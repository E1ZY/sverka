import csv
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .config import DATA, DEMO_DIR, MAX_CASE_FILES, MAX_FILE_BYTES, ROOT
from .db import Case, Document, FixtureBatch, Review, Run, Session, init_db, uid
from .domain import ARTICLES, money
from .extractors import SUPPORTED, digest, page_image
from .pipeline import document_dict, enqueue, loop
from .uploads import validate_file
from .report_context import extract_report_context
from .fixtures import compare_fixture, fixture_inputs, list_fixtures, load_oracle
from .fixture_batches import batch_dict


@asynccontextmanager
async def lifespan(app):
    init_db()
    stop = threading.Event()
    worker = None
    if os.getenv('EMBED_WORKER', 'true').lower() == 'true':
        worker = threading.Thread(target=loop, args=(stop,), daemon=True)
        worker.start()
    yield
    stop.set()
    if worker:
        worker.join(timeout=5)


app = FastAPI(title='Контур сверки', version='1.0.0', lifespan=lifespan)


class Context(BaseModel):
    contract: str = Field(min_length=1, max_length=80)
    stage: int = Field(ge=1, le=100)
    period_start: date
    period_end: date
    complete_package: bool = False

    @model_validator(mode='after')
    def valid_period(self):
        if self.period_end < self.period_start:
            raise ValueError('Конец периода раньше начала')
        if (self.period_end-self.period_start).days > 730:
            raise ValueError('Период MVP ограничен двумя годами')
        if self.period_start.year != self.period_end.year:
            raise ValueError('Профиль КФЗ MVP проверяет одну годовую строку; выберите период внутри одного года')
        return self


class NewCase(Context):
    title: str = Field(default='Новая проверка', min_length=1, max_length=200)


class ClearCases(BaseModel):
    case_ids: list[UUID] = Field(min_length=1, max_length=100)


class Correction(BaseModel):
    article: Literal['0200', '0300', '0800', '0900'] | None = None
    amount: str | None = None
    contract: str | None = Field(default=None, max_length=80)
    period_start: date | None = None
    period_end: date | None = None
    reason: str = Field(min_length=5, max_length=1000)


def get_case(session, case_id):
    case = session.get(Case, case_id)
    if not case:
        raise HTTPException(404, 'Проверка не найдена')
    return case


def get_document(session, case_id, document_id):
    get_case(session, case_id)
    doc = session.get(Document, document_id)
    if not doc or doc.case_id != case_id:
        raise HTTPException(404, 'Документ не найден')
    return doc


def writable(case):
    if case.status in {'running', 'queued'}:
        raise HTTPException(409, 'Дождитесь завершения текущего запуска')


def case_dict(case):
    return {'id': case.id, 'title': case.title, 'context': case.context, 'status': case.status,
            'created_at': case.created_at.isoformat(), 'active_run_id': case.active_run_id}


@app.get('/api/health')
def health():
    with Session() as session:
        session.execute(select(1))
    return {'status': 'ok', 'mode': 'local', 'version': app.version}


@app.get('/api/cases')
def list_cases():
    with Session() as session:
        return [case_dict(c) for c in session.scalars(select(Case).order_by(Case.created_at.desc()).limit(100))]


@app.post('/api/cases', status_code=201)
def create_case(body: NewCase):
    context = body.model_dump(mode='json', exclude={'title'})
    context['row_label'] = f'{body.stage} этап, {body.period_start.year} г.'
    with Session.begin() as session:
        case = Case(title=body.title, context=context)
        session.add(case)
        session.flush()
        return case_dict(case)


@app.delete('/api/cases')
def clear_cases(body: ClearCases):
    requested = {str(case_id) for case_id in body.case_ids}
    with Session.begin() as session:
        # Serialize removal with SQLite uploads and worker status changes.
        if session.get_bind().dialect.name == 'sqlite':
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        cases = session.scalars(select(Case).where(Case.id.in_(requested)).with_for_update()).all()
        ids = [case.id for case in cases]
        active_run = session.scalar(select(Run.id).where(Run.case_id.in_(ids), Run.status.in_(['queued', 'running'])).limit(1))
        if active_run or any(case.status in {'queued', 'running'} for case in cases):
            raise HTTPException(409, 'Некоторые проверки уже выполняются. Обновите список и повторите очистку после их завершения.')
        for batch in session.scalars(select(FixtureBatch).where(FixtureBatch.active_key.is_not(None))):
            if any(item.get('case_id') in requested for item in batch.items):
                batch_dict(session, batch)
                if batch.active_key:
                    raise HTTPException(409, 'Дождитесь завершения проверки всего каталога тестовых кейсов.')
        directories = []
        for case_id in ids:
            directory = DATA / case_id
            if directory.is_symlink() or directory.resolve().parent != DATA.resolve():
                raise HTTPException(409, 'Не удалось безопасно определить папку документов проверки.')
            directories.append((case_id, directory))
        # Keep foreign-key constraints enabled; remove dependants before parents.
        for model in (Review, Run, Document):
            session.execute(delete(model).where(model.case_id.in_(ids)))
        session.execute(delete(Case).where(Case.id.in_(ids)))
    cleanup_failed = []
    for case_id, directory in directories:
        try:
            if directory.exists():
                shutil.rmtree(directory)
        except OSError:
            logging.getLogger(__name__).exception('Could not remove files for deleted case %s', case_id)
            cleanup_failed.append(case_id)
    return {'deleted_ids': ids, 'cleanup_failed': cleanup_failed}


@app.post('/api/reports/context')
def suggest_report_context(file: UploadFile = File(...)):
    """Inspect an upload before a case exists, without keeping a copy or creating a run."""
    ext = Path(file.filename or '').suffix.lower()
    if ext not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise HTTPException(400, 'Для отчёта нужен PDF, PNG или JPEG')
    with tempfile.TemporaryDirectory(prefix='report-context-', dir=DATA) as directory:
        path = Path(directory) / ('report' + ext)
        size = 0
        with path.open('wb') as out:
            while chunk := file.file.read(1024*1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, 'Файл превышает 25 МБ')
                out.write(chunk)
        if not size:
            raise HTTPException(400, 'Пустой файл')
        try:
            return extract_report_context(path)
        except Exception:
            logging.getLogger(__name__).warning('Report context extraction failed', exc_info=True)
            raise HTTPException(422, 'Не удалось прочитать параметры КФЗ. Заполните их вручную.')


@app.get('/api/cases/{case_id}')
def read_case(case_id: str):
    with Session() as session:
        case = get_case(session, case_id)
        docs = session.scalars(select(Document).where(Document.case_id == case_id).order_by(Document.name)).all()
        runs = session.scalars(select(Run).where(Run.case_id == case_id).order_by(Run.created_at.desc())).all()
        reviews = session.scalars(select(Review).where(Review.case_id == case_id).order_by(Review.created_at)).all()
        result = next((r.payload for r in runs if r.id == case.active_run_id), None)
        comparison = compare_fixture(case.context['fixture_id'], result) if case.context.get('fixture_id') and result else None
        return {**case_dict(case), 'documents': [document_dict(d) for d in docs],
                'runs': [{'id': r.id, 'created_at': r.created_at.isoformat(), 'status': r.status, 'progress': r.progress, 'message': r.message} for r in runs],
                'result': result, 'fixture_comparison': comparison,
                'reviews': [{'id': r.id, 'document_id': r.document_id, 'changes': r.changes, 'before': r.before, 'reason': r.reason, 'created_at': r.created_at.isoformat()} for r in reviews]}


@app.post('/api/cases/{case_id}/documents', status_code=201)
def upload(case_id: str, role: Literal['report', 'primary'] = Form(...), files: list[UploadFile] = File(...)):
    written = []
    try:
        with Session.begin() as session:
            case = get_case(session, case_id)
            writable(case)
            existing = session.scalars(select(Document).where(Document.case_id == case_id)).all()
            if len(existing) + len(files) > MAX_CASE_FILES:
                raise HTTPException(400, 'Не более 100 файлов в одной проверке')
            if role == 'report' and (len(files) != 1 or any(d.role == 'report' for d in existing)):
                raise HTTPException(400, 'Необходим ровно один итоговый отчёт')
            result = []
            directory = DATA / case_id
            directory.mkdir(exist_ok=True)
            for upload_file in files:
                name = (upload_file.filename or 'document').replace('\\', '/').split('/')[-1][:255]
                ext = Path(name).suffix.lower()
                if ext not in SUPPORTED or (role == 'report' and ext not in {'.pdf', '.png', '.jpg', '.jpeg'}):
                    raise HTTPException(400, f'Неподдерживаемый формат: {ext}')
                path = directory / (uid() + ext)
                written.append(path)
                size = 0
                with path.open('wb') as out:
                    while chunk := upload_file.file.read(1024*1024):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            raise HTTPException(413, 'Файл превышает 25 МБ')
                        out.write(chunk)
                if not size:
                    raise HTTPException(400, 'Пустой файл')
                try:
                    validate_file(path)
                except (ValueError, zipfile.BadZipFile) as e:
                    raise HTTPException(400, str(e))
                doc = Document(case_id=case_id, name=name, path=str(path), sha256=digest(path), role=role)
                session.add(doc)
                session.flush()
                result.append(document_dict(doc))
            case.status = 'draft'
            return result
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise


@app.post('/api/cases/{case_id}/runs', status_code=202)
def start(case_id: str):
    with Session.begin() as session:
        case = get_case(session, case_id)
        docs = session.scalars(select(Document).where(Document.case_id == case_id)).all()
        if sum(d.role == 'report' for d in docs) != 1 or not any(d.role == 'primary' for d in docs):
            raise HTTPException(400, 'Загрузите один отчёт и первичные документы')
        try:
            run = enqueue(session, case)
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {'id': run.id, 'status': run.status}


@app.post('/api/cases/{case_id}/documents/{document_id}/review', status_code=201)
def review(case_id: str, document_id: str, body: Correction):
    with Session.begin() as session:
        case = get_case(session, case_id)
        writable(case)
        doc = get_document(session, case_id, document_id)
        if doc.role != 'primary' or not doc.extraction or doc.error:
            raise HTTPException(400, 'Исправление доступно для извлечённых первичных документов')
        changes = body.model_dump(mode='json', exclude_none=True, exclude={'reason'})
        if not changes:
            raise HTTPException(400, 'Укажите хотя бы одно изменение')
        if 'amount' in changes:
            try:
                changes['amount'] = str(money(changes['amount']))
            except Exception:
                raise HTTPException(422, 'Некорректная сумма')
        effective = dict(doc.extraction)
        prior = session.scalars(select(Review).where(Review.document_id == doc.id).order_by(Review.created_at, Review.id)).all()
        for item in prior:
            effective.update(item.changes)
        updated = {**effective, **changes}
        if updated.get('period_start') and updated.get('period_end') and updated['period_start'] > updated['period_end']:
            raise HTTPException(422, 'Неверный период')
        event = Review(case_id=case_id, document_id=document_id, changes=changes,
                       before={k: effective.get(k) for k in changes}, reason=body.reason)
        session.add(event)
        session.flush()
        run = enqueue(session, case)
        return {'review_id': event.id, 'run_id': run.id}


@app.get('/api/cases/{case_id}/documents/{document_id}/original')
def original(case_id: str, document_id: str):
    with Session() as session:
        doc = get_document(session, case_id, document_id)
        return FileResponse(doc.path, filename=doc.name, content_disposition_type='attachment')


@app.get('/api/cases/{case_id}/documents/{document_id}/page/{page}')
def image_page(case_id: str, document_id: str, page: int):
    with Session() as session:
        doc = get_document(session, case_id, document_id)
        try:
            image = page_image(doc.path, page)
            out = io.BytesIO()
            image.save(out, format='PNG')
        except Exception as e:
            raise HTTPException(400, str(e))
        return Response(out.getvalue(), media_type='image/png')


@app.get('/api/cases/{case_id}/runs/{run_id}/export')
def export(case_id: str, run_id: str, format: Literal['json', 'csv'] = 'json'):
    with Session() as session:
        get_case(session, case_id)
        run = session.get(Run, run_id)
        if not run or run.case_id != case_id or not run.payload:
            raise HTTPException(404, 'Готовый результат не найден')
        if format == 'json':
            content = json.dumps(run.payload, ensure_ascii=False, indent=2)
            media = 'application/json'
        else:
            out = io.StringIO()
            writer = csv.writer(out, delimiter=';')
            writer.writerow(['Код', 'Показатель', 'В отчёте', 'Ожидается', 'Разница', 'Статус', 'Примечание'])
            for r in run.payload['metrics']:
                writer.writerow([r.get(k) for k in ['code', 'name', 'actual', 'expected', 'delta', 'status', 'reason']])
            content, media = '\ufeff' + out.getvalue(), 'text/csv'
        return Response(content, media_type=media, headers={'Content-Disposition': f'attachment; filename="reconciliation-{run.id}.{format}"'})


@app.get('/api/demo/documents.zip')
def demo_documents():
    manifest = json.loads((ROOT/'demo'/'manifest.json').read_text(encoding='utf-8'))
    files = [(DEMO_DIR/item['name'], item['role']) for item in manifest['files']]
    if any(not path.is_file() for path, _ in files):
        raise HTTPException(404, 'Демонстрационные документы не установлены полностью')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as kit:
        for path, role in files:
            kit.write(path, f'{role}/{path.name}')
    return Response(archive.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="sverka-training-documents.zip"'})


@app.post('/api/demo', status_code=201)
def demo():
    manifest = json.loads((ROOT/'demo'/'manifest.json').read_text(encoding='utf-8'))
    if not DEMO_DIR.is_dir():
        raise HTTPException(404, 'Демонстрационные документы не установлены')
    with Session.begin() as session:
        case = Case(title='Сверка затрат · этап 3', context=manifest['context'])
        session.add(case)
        session.flush()
        directory = DATA/case.id
        directory.mkdir(exist_ok=True)
        for item in manifest['files']:
            source = DEMO_DIR/item['name']
            if not source.is_file():
                raise HTTPException(404, 'Отсутствует демонстрационный файл: '+item['name'])
            dest = directory/(uid()+source.suffix)
            shutil.copyfile(source, dest)
            session.add(Document(case_id=case.id, name=source.name, path=str(dest), sha256=digest(dest), role=item['role']))
        run = enqueue(session, case)
        return {'case_id': case.id, 'run_id': run.id}


@app.get('/api/fixtures')
def fixtures():
    return list_fixtures()


def create_fixture_run(session, fixture_id, created_files, created_directories):
    manifest, inputs = fixture_inputs(fixture_id)
    # Same document validator as the manual multipart upload. Invalid files
    # are rejected before a case or a calculation job can be created.
    for source, role, sha in inputs:
        try:
            validate_file(source)
        except (ValueError, zipfile.BadZipFile) as exc:
            expected_status = load_oracle(fixture_id)['upload_status']
            return {
                'status': 'rejected', 'fixture_id': fixture_id, 'filename': source.name,
                'message': str(exc), 'actual_http_status': 400, 'expected_http_status': expected_status,
                'matches_expected': expected_status == 400,
            }
    written = []
    directory = None
    try:
        context = Context.model_validate(manifest['context']).model_dump(mode='json')
        context.update(row_label=manifest['context']['row_label'], fixture_id=fixture_id)
        case = Case(title=manifest['title'], context=context)
        session.add(case)
        session.flush()
        directory = DATA/case.id
        directory.mkdir(exist_ok=False)
        created_directories.append(directory)
        for source, role, sha in inputs:
            dest = directory/(uid()+source.suffix.lower())
            written.append(dest)
            created_files.append(dest)
            shutil.copyfile(source, dest)
            session.add(Document(case_id=case.id, name=source.name, path=str(dest), sha256=sha, role=role))
        run = enqueue(session, case)
        return {'status': 'queued', 'case_id': case.id, 'run_id': run.id, 'fixture_id': fixture_id}
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        if directory and directory.exists():
            directory.rmdir()
        raise


def cleanup_fixture_import(created_files, created_directories):
    for path in created_files:
        path.unlink(missing_ok=True)
    for directory in reversed(created_directories):
        if directory.exists():
            directory.rmdir()


@app.post('/api/fixtures/{fixture_id}/runs', status_code=202)
def launch_fixture(fixture_id: str):
    created_files, created_directories = [], []
    try:
        with Session.begin() as session:
            result = create_fixture_run(session, fixture_id, created_files, created_directories)
        return JSONResponse(status_code=200, content=result) if result['status'] == 'rejected' else result
    except Exception:
        cleanup_fixture_import(created_files, created_directories)
        raise


@app.get('/api/fixture-batches/latest')
def latest_fixture_batch():
    with Session.begin() as session:
        batch = session.scalar(select(FixtureBatch).order_by(FixtureBatch.created_at.desc(), FixtureBatch.id.desc()).limit(1))
        return batch_dict(session, batch) if batch else None


@app.get('/api/fixture-batches/{batch_id}')
def read_fixture_batch(batch_id: str):
    with Session.begin() as session:
        batch = session.get(FixtureBatch, batch_id)
        if not batch:
            raise HTTPException(404, 'Общий прогон не найден')
        return batch_dict(session, batch)


@app.post('/api/fixture-batches', status_code=202)
def start_fixture_batch():
    items = list_fixtures()
    if not items:
        raise HTTPException(400, 'Нет установленных тестовых кейсов')
    created_files, created_directories = [], []
    try:
        with Session.begin() as session:
            active = session.scalar(select(FixtureBatch).where(FixtureBatch.active_key == 'all'))
            if active and batch_dict(session, active)['status'] != 'completed':
                raise HTTPException(409, 'Общий прогон уже выполняется. Откройте его результаты.')
            batch = FixtureBatch(active_key='all')
            session.add(batch)
            session.flush()
            outcomes = []
            for item in items:
                snapshot = {key: item[key] for key in ('title', 'known_limitation')}
                snapshot['fixture_id'] = item['id']
                try:
                    # A bad case rolls back only its own database records.
                    with session.begin_nested():
                        result = create_fixture_run(session, item['id'], created_files, created_directories)
                    snapshot.update(result)
                    if result['status'] == 'rejected':
                        snapshot['upload_result'] = result
                except Exception as exc:
                    message = exc.detail if isinstance(exc, HTTPException) else str(exc)
                    logging.getLogger(__name__).warning('Fixture %s could not start: %s', item['id'], message)
                    snapshot.update(status='error', message=str(message)[:1000])
                outcomes.append(snapshot)
            batch.items = outcomes
            batch_id = batch.id
    except IntegrityError:
        cleanup_fixture_import(created_files, created_directories)
        raise HTTPException(409, 'Общий прогон уже выполняется. Откройте его результаты.')
    except Exception:
        cleanup_fixture_import(created_files, created_directories)
        raise
    return read_fixture_batch(batch_id)


frontend = ROOT/'frontend'/'dist'
if frontend.is_dir():
    app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
