from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.redis_client import get_redis
from app.limiter import limiter

router = APIRouter(tags=["system"])


@router.get("/status")
@limiter.limit("10/minute")  # type: ignore[arg-type]
@limiter.limit("300/hour")  # type: ignore[arg-type]
async def health_check(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    """
    健康檢查端點，檢查資料庫和 Redis 連線狀態
    """
    db_status = "ok"
    redis_status = "ok"

    # 檢查資料庫連線
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        print(f"Database connection error: {e}")
        db_status = "down"

    # 檢查 Redis 連線
    try:
        await redis.ping()
    except Exception as e:
        print(f"Redis connection error: {e}")
        redis_status = "down"

    return {
        "api": "ok",
        "version": request.app.version,
        "database": db_status,
        "redis": redis_status,
    }
