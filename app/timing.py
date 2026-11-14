"""Run wall time from worker start to finish, excluding the initial queue wait."""
from datetime import timezone

from .db import now


def timestamp(value):
    # SQLite returns naive datetimes even for timezone-aware columns.
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def run_timing(run, at=None):
    started = timestamp(run.started_at) if run else None
    finished = timestamp(run.finished_at) if run else None
    duration = max(0., ((finished or timestamp(at or now())) - started).total_seconds()) if started else None
    return {'started_at': started.isoformat() if started else None,
            'finished_at': finished.isoformat() if finished else None,
            'duration_seconds': duration}
