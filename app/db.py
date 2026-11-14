from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = 'cases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200))
    context: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='draft')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=now)
    active_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(20))
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocumentAsset(Base):
    """Retained original, independent of any one case; links use Document.sha256."""
    __tablename__ = 'document_assets'
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@event.listens_for(Case.status, 'set')
def record_status_change(case, value, previous, initiator):
    if value != previous:
        case.status_changed_at = now()


class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default='Ожидает обработки')
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    changes: Mapped[dict] = mapped_column(JSON)
    before: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)


class FixtureBatch(Base):
    __tablename__ = 'fixture_batches'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # The database permits only one active whole-catalog run at a time.
    active_key: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    items: Mapped[list] = mapped_column(JSON, default=list)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    credential_tag: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


engine = create_engine(DATABASE_URL, **({'connect_args': {'check_same_thread': False, 'timeout': 30}} if DATABASE_URL.startswith('sqlite') else {}))
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def configure_sqlite(connection, _):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA foreign_keys=ON')

Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    # Additive migration for existing SQLite/PostgreSQL installations; no data reset.
    if 'status_changed_at' not in {column['name'] for column in inspect(engine).get_columns('cases')}:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE cases ADD COLUMN status_changed_at TIMESTAMP'))
    run_columns = {column['name'] for column in inspect(engine).get_columns('runs')}
    time_type = DateTime(timezone=True).compile(dialect=engine.dialect)
    with engine.begin() as connection:
        for name in ('started_at', 'finished_at'):
            if name not in run_columns:
                connection.execute(text(f'ALTER TABLE runs ADD COLUMN {name} {time_type}'))
