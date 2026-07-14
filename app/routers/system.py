from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis
import asyncmy  # type: ignore
import asyncpg  # type: ignore

from sqlalchemy.engine import make_url

from app.config import settings
from app.redis_client import get_redis
from app.limiter import limiter

router = APIRouter(tags=["system"])


async def check_mysql_connection() -> bool:
    url = make_url(settings.db_url)

    if url.drivername.startswith("mysql"):
        conn = await asyncmy.connect(
            host=url.host,
            port=url.port or 3306,
            user=url.username,
            password=url.password,
            db=url.database,
        )

        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                row = await cursor.fetchone()
                return row is not None and row[0] == 1
        finally:
            conn.close()

    if url.drivername.startswith("postgresql"):
        sslmode = url.query.get("sslmode")
        connect_kwargs = {
            "host": url.host,
            "port": url.port or 5432,
            "user": url.username,
            "password": url.password,
            "database": url.database,
        }

        if sslmode in {"require", "verify-ca", "verify-full"}:
            connect_kwargs["ssl"] = True

        conn = await asyncpg.connect(**connect_kwargs)

        try:
            value = await conn.fetchval("SELECT 1")
            return value == 1
        finally:
            await conn.close()

    raise ValueError(
        "/status only supports MySQL or PostgreSQL DB_URL in the current setup"
    )


@router.get("/status")
@limiter.limit("10/minute")  # type: ignore[arg-type]
@limiter.limit("300/hour")  # type: ignore[arg-type]
async def health_check(
    request: Request, response: Response, redis: Redis = Depends(get_redis)
) -> dict[str, str]:
    """
    健康檢查端點，檢查資料庫和 Redis 連線狀態
    """
    db_status = "ok"
    redis_status = "ok"

    # 檢查資料庫連線
    try:
        if not await check_mysql_connection():
            db_status = "down"
    except Exception as e:
        print(f"Database connection error: {e}")
        db_status = "down"

    # 檢查 Redis 連線
    try:
        await redis.ping()
    except Exception as e:
        print(f"Redis connection error: {e}")
        redis_status = "down"

    from app.main import pyproject_data

    return {
        "api": "ok",
        "version": pyproject_data.get("version", "0.1.0"),
        "database": db_status,
        "redis": redis_status,
    }
