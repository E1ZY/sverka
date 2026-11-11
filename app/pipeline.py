import copy
import logging
import time
from datetime import timedelta

from sqlalchemy import or_, select

from .config import PIPELINE_VERSION
from .db import Case, Document, Review, Run, Session, engine, init_db, now
from .domain import RULES, reconcile
from .extractors import extract_primary, extract_report

log = logging.getLogger(__name__)


def document_dict(doc):
    return {k: getattr(doc, k) for k in ('id', 'name', 'role', 'sha256', 'extraction', 'error')}


def enqueue(session, case):
    if case.status in {'queued', 'running'}:
        raise ValueError('Проверка уже выполняется')
    reviews = session.scalars(select(Review).where(Review.case_id == case.id).order_by(Review.created_at, Review.id)).all()
    run = Run(case_id=case.id, review_snapshot=[{'id': r.id, 'document_id': r.document_id, 'changes': r.changes, 'reason': r.reason} for r in reviews])
    session.add(run)
    session.flush()
    case.active_run_id = run.id
    case.status = 'queued'
    return run


def claim():
    with Session.begin() as session:
        stmt = select(Run).where(or_(Run.status == 'queued', (Run.status == 'running') & (Run.lease_until < now()))).order_by(Run.created_at).limit(1)
        if engine.dialect.name == 'postgresql':
            stmt = stmt.with_for_update(skip_locked=True)
        run = session.scalar(stmt)
        if run is None:
            return None
        if run.attempts >= 3:
            run.status, run.message = 'failed', 'Обработка прервана три раза. Запустите новую проверку.'
            session.get(Case, run.case_id).status = 'failed'
            return None
        run.status, run.lease_until = 'running', now() + timedelta(minutes=10)
        run.attempts += 1
        session.get(Case, run.case_id).status = 'running'
        return run.id


def process(run_id):
    try:
        with Session() as session:
            run = session.get(Run, run_id)
            case = session.get(Case, run.case_id)
            context = copy.deepcopy(case.context)
            docs = session.scalars(select(Document).where(Document.case_id == case.id).order_by(Document.name, Document.id)).all()
            reviews = copy.deepcopy(run.review_snapshot)
            cache = {}
            for i, doc in enumerate(docs):
                run.message = f'Извлечение {i+1}/{len(docs)}: {doc.name}'
                run.progress = int(i / max(1, len(docs)) * 85)
                run.lease_until = now() + timedelta(minutes=10)
                session.commit()
                key = (doc.sha256, doc.role)
                if doc.extraction is None:
                    try:
                        fact = cache.get(key)
                        if fact is None:
                            fact = extract_report(doc.path, context) if doc.role == 'report' else extract_primary(doc.path)
                        doc.extraction = fact
                        cache[key] = fact
                        doc.error = None
                    except Exception as e:
                        log.warning('Extraction failed for %s: %s', doc.id, e)
                        doc.error = str(e)[:1000]
                    session.commit()
                elif not doc.error:
                    cache[key] = doc.extraction
            snapshot = [document_dict(d) for d in docs]
            for review in reviews:
                doc = next((d for d in snapshot if d['id'] == review['document_id']), None)
                if doc:
                    doc['extraction'] = copy.deepcopy(doc['extraction'] or {})
                    doc['extraction'].update(review['changes'])
                    doc['extraction'].update(needs_review=False, reviewed=True)
            result = reconcile(context, snapshot)
            result.update(context=context, pipeline_version=PIPELINE_VERSION, rules_version=RULES['version'], reviews=reviews,
                          created_at=now().isoformat(), run_id=run.id)
            run.payload = result
            run.status, run.progress, run.message, run.lease_until = 'completed', 100, 'Сверка завершена', None
            case.status = 'completed'
            session.commit()
    except Exception as e:
        log.exception('Run failed: %s', run_id)
        with Session.begin() as session:
            run = session.get(Run, run_id)
            run.status, run.message, run.lease_until = 'failed', str(e)[:1000], None
            session.get(Case, run.case_id).status = 'failed'


def loop(stop=None):
    init_db()
    while stop is None or not stop.is_set():
        try:
            run_id = claim()
            if run_id:
                process(run_id)
                continue
        except Exception:
            log.exception('Worker polling failed')
        if stop:
            stop.wait(.5)
        else:
            time.sleep(.5)
