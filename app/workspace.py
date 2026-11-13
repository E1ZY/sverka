"""Workspace document catalogue, immutable case copies and portable packages."""
import copy
import csv
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from .config import DATA
from .db import Case, Document, DocumentAsset, Review, uid


def sync_assets(session, documents=None):
    for doc in documents if documents is not None else session.scalars(select(Document)).all():
        asset = session.get(DocumentAsset, doc.sha256)
        if asset is None:
            source = Path(doc.path)
            if not source.is_file():
                continue
            directory = DATA/'_documents'
            directory.mkdir(exist_ok=True)
            path = directory/(doc.sha256 + source.suffix.lower())
            if not path.exists():
                temporary = directory/(uid() + '.tmp')
                try:
                    shutil.copyfile(source, temporary)
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            insert = sqlite_insert if session.get_bind().dialect.name == 'sqlite' else postgres_insert
            session.execute(insert(DocumentAsset).values(sha256=doc.sha256, name=doc.name, path=str(path))
                            .on_conflict_do_nothing(index_elements=['sha256']))


def asset_catalog(session):
    sync_assets(session)
    links = {}
    for doc, case in session.execute(select(Document, Case).join(Case, Document.case_id == Case.id)):
        links.setdefault(doc.sha256, {})[case.id] = {'id': case.id, 'title': case.title}
    return [{'id': asset.sha256, 'name': asset.name, 'size': Path(asset.path).stat().st_size if Path(asset.path).is_file() else None,
             'cases': list(links.get(asset.sha256, {}).values()), 'user': 'Общий доступ',
             'created_at': asset.created_at.isoformat()}
            for asset in session.scalars(select(DocumentAsset).order_by(DocumentAsset.created_at.desc()))]


def remove_unused_assets(session, hashes=None):
    linked = set(session.scalars(select(Document.sha256)).all())
    removed = []
    for asset in session.scalars(select(DocumentAsset).with_for_update()).all():
        if asset.sha256 in linked or (hashes is not None and asset.sha256 not in hashes):
            continue
        path = Path(asset.path)
        if path.is_symlink() or path.resolve().parent != (DATA/'_documents').resolve():
            raise HTTPException(409, 'Не удалось безопасно определить путь документа.')
        path.unlink(missing_ok=True)
        removed.append(asset.sha256)
        session.delete(asset)
    return removed


def copy_case_documents(session, source_case, target_case, selected_ids):
    docs = session.scalars(select(Document).where(Document.case_id == source_case.id)).all()
    chosen = set(selected_ids)
    if chosen - {doc.id for doc in docs}:
        raise HTTPException(400, 'Некоторые документы не принадлежат исходной сверке.')
    docs = [doc for doc in docs if doc.id in chosen]
    if sum(doc.role == 'report' for doc in docs) > 1:
        raise HTTPException(400, 'Допускается один главный отчёт.')
    directory = DATA/target_case.id
    directory.mkdir(exist_ok=True)
    mapping = {}
    for doc in docs:
        path = directory/(uid() + Path(doc.path).suffix)
        if not Path(doc.path).is_file():
            raise HTTPException(409, 'Оригинал документа недоступен: ' + doc.name)
        shutil.copyfile(doc.path, path)
        target = Document(case_id=target_case.id, name=doc.name, path=str(path), sha256=doc.sha256,
                          role=doc.role, extraction=copy.deepcopy(doc.extraction) if doc.role == 'primary' else None,
                          error=doc.error if doc.role == 'primary' else None)
        session.add(target)
        session.flush()
        mapping[doc.id] = target.id
    # Manual corrections belong to the copied input, not to a previous result snapshot.
    for review in session.scalars(select(Review).where(Review.case_id == source_case.id).order_by(Review.created_at, Review.id)):
        if review.document_id in mapping:
            session.add(Review(case_id=target_case.id, document_id=mapping[review.document_id],
                               changes=copy.deepcopy(review.changes), before=copy.deepcopy(review.before), reason=review.reason))


def case_package(case, documents, payload, tree):
    with tempfile.NamedTemporaryFile(prefix='sverka-package-', suffix='.zip', dir=DATA, delete=False) as temporary:
        output = Path(temporary.name)
    try:
        write_package(output, case, documents, payload, tree)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return output


def write_package(output, case, documents, payload, tree):
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for doc in documents:
            if not Path(doc.path).is_file():
                raise HTTPException(409, 'Оригинал документа недоступен: ' + doc.name)
            # Index avoids collisions from equal names and prevents ZIP traversal.
            name = doc.name.replace('\\', '/').split('/')[-1]
            archive.write(doc.path, f'documents/{doc.role}/{doc.id[:8]}-{name}')
        archive.writestr('reconciliation.json', json.dumps({'case_id': case.id, 'title': case.title, 'context': case.context,
            'result': payload, 'cost_tree': tree}, ensure_ascii=False, indent=2))
        report = io.StringIO()
        writer = csv.writer(report, delimiter=';')
        writer.writerow(['Код', 'Показатель', 'Заявлено', 'По документам', 'Разница', 'Статус', 'Комментарий'])
        for metric in (payload or {}).get('metrics', []):
            writer.writerow([metric.get(key) for key in ('code', 'name', 'actual', 'expected', 'delta', 'status', 'reason')])
        archive.writestr('reconciliation.csv', '\ufeff' + report.getvalue())
        archive.writestr('README.txt', f'Сверка {case.id}\n{case.title}\nОригиналы — documents/. Результат — reconciliation.csv и reconciliation.json.\n')
