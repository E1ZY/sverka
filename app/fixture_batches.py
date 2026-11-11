"""Persisted whole-catalog runs, observing their original calculation jobs."""
from sqlalchemy import select

from .db import Run
from .fixtures import compare_fixture


def batch_dict(session, batch):
    run_ids = [item['run_id'] for item in batch.items if item.get('run_id')]
    runs = {run.id: run for run in session.scalars(select(Run).where(Run.id.in_(run_ids)))} if run_ids else {}
    items = []
    counts = {key: 0 for key in ('passed', 'known_limitations', 'failed', 'errors', 'unexpected_passes', 'queued', 'running')}
    for stored in batch.items:
        item = {key: stored.get(key) for key in ('fixture_id', 'title', 'known_limitation', 'case_id', 'run_id')}
        item.update(progress=100, differences=0, message='')
        if stored['status'] == 'error':
            item.update(status='error', message=stored['message'])
        elif stored['status'] == 'rejected':
            rejection = stored['upload_result']
            item.update(status='passed' if rejection['matches_expected'] else 'failed',
                        message=f"Файл {rejection['filename']} отклонён: HTTP {rejection['actual_http_status']}, "
                                f"ожидался {rejection['expected_http_status']}. Сверка сумм не запускалась.")
        else:
            run = runs.get(stored['run_id'])
            if run is None:
                item.update(status='error', message='Задание проверки не найдено.')
            elif run.status in {'queued', 'running'}:
                item.update(status=run.status, progress=run.progress, message=run.message)
            elif run.status != 'completed' or not run.payload:
                item.update(status='error', message=run.message or 'Обработка завершилась без результата.')
            else:
                try:
                    comparison = compare_fixture(stored['fixture_id'], run.payload)
                except Exception as exc:
                    comparison = {'available': False, 'message': 'Не удалось прочитать эталон: '+str(exc)[:500]}
                if not comparison['available']:
                    item.update(status='error', message=comparison['message'])
                elif comparison['matches']:
                    item.update(status='unexpected_pass' if stored['known_limitation'] else 'passed',
                                message='Результат совпал с эталоном.')
                else:
                    item.update(status='known_limitation' if stored['known_limitation'] else 'failed',
                                differences=len(comparison['differences']),
                                message=stored['known_limitation'] or 'Результат отличается от эталона.')
        count_key = {'known_limitation': 'known_limitations', 'error': 'errors',
                     'unexpected_pass': 'unexpected_passes'}.get(item['status'], item['status'])
        counts[count_key] += 1
        items.append(item)
    total = len(items)
    done = total - counts['queued'] - counts['running']
    completed = done == total
    # Release the unique slot both on reads and before a subsequent launch.
    if completed:
        batch.active_key = None
        session.flush()
    return {'id': batch.id, 'created_at': batch.created_at.isoformat(),
            'status': 'completed' if completed else 'running', 'total': total, 'done': done,
            'progress': int(done * 100 / total) if total else 100, 'counts': counts, 'items': items}
