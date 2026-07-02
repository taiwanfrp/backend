import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.config import settings

database_url = make_url(settings.db_url)

if settings.db_type == "mysql":
    db_url = database_url.set(drivername="mysql+asyncmy")
    connect_args = {"ssl": True} if settings.db_mysql_ssl else {}
elif settings.db_type == "postgresql":
    filtered_query = {
        key: value
        for key, value in database_url.query.items()
        if key not in {"sslmode", "channel_binding"}
    }
    db_url = database_url.set(
        drivername="postgresql+asyncpg",
        query=filtered_query,
    )
    connect_args = {}
else:
    raise ValueError(f"Unsupported database type: {settings.db_type}")

# 強制覆寫 alembic.ini 裡面的 sqlalchemy.url
config.set_main_option("sqlalchemy.url", db_url.render_as_string(hide_password=False))

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.database import Base
import app.models  # 確保模型被導入, 以便 Alembic 能夠找到 metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
