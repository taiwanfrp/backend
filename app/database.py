from collections.abc import AsyncGenerator
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

database_url = make_url(settings.db_url)

if settings.db_type == "mysql":
    DATABASE_URL = database_url.set(drivername="mysql+asyncmy")
    CONNECT_ARGS = {"ssl": True} if settings.db_mysql_ssl else {}
elif settings.db_type == "postgresql":
    sslmode = database_url.query.get("sslmode")
    filtered_query = {
        key: value
        for key, value in database_url.query.items()
        if key not in {"sslmode", "channel_binding"}
    }

    DATABASE_URL = database_url.set(
        drivername="postgresql+asyncpg",
        query=filtered_query,
    )
    CONNECT_ARGS = (
        {"ssl": True} if sslmode in {"require", "verify-ca", "verify-full"} else {}
    )
else:
    raise ValueError(f"Unsupported database type: {settings.db_type}")

engine = create_async_engine(
    DATABASE_URL,
    connect_args=CONNECT_ARGS,
    echo=False,  # Set to True for SQL query logging
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Check if connections are alive
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
