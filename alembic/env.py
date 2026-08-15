import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 1. Asegurar que el directorio raíz del proyecto esté en el path de Python
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

# 2. Importar Base y tus modelos para que Alembic detecte los cambios
from app.db.database import Base
import app.models  # Asegura que se carguen todas las definiciones de tablas

# Configuración del objeto de Alembic
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Asignar los metadatos de los modelos
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline: genera los scripts SQL sin conectarse directamente."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Habilitado para compatibilidad con SQLite (ALTER TABLE)
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: ejecuta las migraciones directamente en la base de datos."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Habilitado para compatibilidad con SQLite (ALTER TABLE)
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()