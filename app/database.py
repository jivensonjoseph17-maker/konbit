"""
Konbit — Koneksyon baz done
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Baz deklaratif SQLAlchemy 2.0."""
    pass


# SQLite bezwen yon opsyon espesyal pou l travay ak FastAPI.
# PostgreSQL pa bezwen l, epi li bezwen yon pool.
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=settings.debug,
    )

    # Aktive kle etranjè nan SQLite (yo DEZAKTIVE pa defo — sa siprann anpil moun).
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    engine = create_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,     # verifye koneksyon an vivan anvan l sèvi avè l
        pool_recycle=1800,
        echo=settings.debug,
    )


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """Depandans FastAPI. Chak rekèt jwenn pwòp sesyon pa l."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()