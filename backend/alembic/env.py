"""
Konbit — Alembic env.py
Chemen: backend/alembic/env.py

Ranplase fichye `alembic init alembic` te kreye a ak sa a.

Sa fichye sa a fè diferan de sa Alembic bay pa defo:
  - Li pran `database_url` nan config.py ou a (donk nan .env), pa nan alembic.ini.
    Konsa ou pa gen kredansyèl baz done nan yon fichye ki komite nan Git.
  - Li enpòte `Base` ak tout modèl yo pou `--autogenerate` ka wè yo.
  - Li mete `render_as_batch=True` pou SQLite ka fè ALTER TABLE.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# --- Konbit: enpòte konfigirasyon ak modèl yo ---
# Chemen an fonksyone paske alembic kouri depi backend/
from app.config import settings
from app.database import Base
from app import models  # noqa: F401  — obligatwa: li anrejistre tab yo nan Base

config = context.config

# Mete URL la depi .env, ranplase sa ki nan alembic.ini
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# SQLite pa sipòte ALTER TABLE konplèt. batch mode kreye yon tab tanporè,
# kopye done yo, epi ranplase ansyen an. Sa pa fè mal sou PostgreSQL.
IS_SQLITE = settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Jenere SQL san konekte ak baz done a."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=IS_SQLITE,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Konekte ak baz done a epi aplike migrasyon yo."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,              # detekte chanjman nan tip kolòn
            compare_server_default=True,
            render_as_batch=IS_SQLITE,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()