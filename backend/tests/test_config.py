"""
Konbit — Tès konfigirasyon
Chemen: backend/tests/test_config.py
"""

from app.config import Settings

KEY = "Qm7vR2xLp9wZ4nH8bK3yT6cF1jD5sG0aE"   # ase long, san mo fasil


def _url(value: str) -> str:
    return Settings(secret_key=KEY, database_url=value).database_url


def test_render_postgres_url_uses_psycopg3():
    assert _url("postgresql://u:p@host:5432/konmbit") == "postgresql+psycopg://u:p@host:5432/konmbit"
    assert _url("postgres://u:p@host/konmbit") == "postgresql+psycopg://u:p@host/konmbit"


def test_explicit_driver_and_sqlite_are_unchanged():
    assert _url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert _url("sqlite:///./konbit.db") == "sqlite:///./konbit.db"