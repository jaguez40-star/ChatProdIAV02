"""Alembic env.py — gestiona la BD de auth (SQLite).

target_metadata = None (patrón Robustez V02, L6): las migraciones se escriben
a mano, sin autogenerate — coherente con que los modelos ORM solo cubren auth
(los datos operacionales, cuando lleguen en F1+, van por SQL crudo contra
`db_prod`, no por Alembic).

La URL de conexión se toma de Settings (.env), no del valor fijo de
alembic.ini — así un solo .env gobierna dev/producción sin editar el .ini.
"""

from __future__ import annotations

from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from alembic import context
from src.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = None


def run_migrations_offline() -> None:
    """Genera SQL sin conectar a una BD real (modo --sql)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta las migraciones contra la BD real."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        try:
            connection.execute(sa.text("PRAGMA foreign_keys = ON"))
            connection.execute(sa.text("PRAGMA journal_mode = WAL"))
        except Exception:
            pass
        finally:
            # Cerrar el autobegin que abrieron los PRAGMAs (SQLAlchemy 2.0).
            # Sin esto, begin_transaction() de alembic no es dueño de la
            # transacción y el UPDATE de alembic_version se pierde en el
            # rollback: los CREATE TABLE persisten pero la versión queda
            # vieja. Invisible mientras solo exista UNA migración — el bug
            # aparece recién con la segunda, cuando `upgrade head` cree estar
            # en 0001 y en realidad ya corrió 0002.
            connection.commit()

        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
