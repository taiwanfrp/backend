from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.redis_client import get_redis
from app.limiter import limiter

from app.schemas.system import (
    HealthCheckResponseModel,
)

router = APIRouter(tags=["system"])


async def check_database_connection(db: AsyncSession) -> str:
    """
    檢查資料庫連線狀態
    """
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        return "up"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        print(f"Database connection error: {e}")
        return "down"


async def check_redis_connection(redis: Redis) -> str:
    """
    檢查 Redis 連線狀態
    """
    try:
        await asyncio.wait_for(redis.ping(), timeout=2.0)
        return "up"
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        print(f"Redis connection error: {e}")
        return "down"


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    重新導向到網站的 favicon.ico
    """
    return RedirectResponse(
        url="https://taiwanfrp.me/favicon.ico", status_code=status.HTTP_302_FOUND
    )


@router.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "Hello, World!"}


@router.get("/items/{item_id}")
async def read_item(item_id: int) -> dict[str, str | int]:
    return {"item_id": item_id, "description": f"This is item {item_id}"}


@router.get("/status")
@limiter.limit("10/minute")  # type: ignore[arg-type]
@limiter.limit("300/hour")  # type: ignore[arg-type]
async def health_check(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> HealthCheckResponseModel:
    """
    健康檢查端點，檢查資料庫和 Redis 連線狀態
    """
    db_status, redis_status = await asyncio.gather(
        check_database_connection(db),
        check_redis_connection(redis),
    )

    return HealthCheckResponseModel(
        api="ok",
        version=request.app.version,
        database=db_status,
        redis=redis_status,
    )


@router.get("/livez", include_in_schema=False)
async def liveness_probe():
    """
    Liveness probe endpoint for Kubernetes
    """
    return {"status": "alive"}


@router.get("/readyz", include_in_schema=False)
async def readiness_probe(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    Readiness probe endpoint for Kubernetes
    """
    db_status, redis_status = await asyncio.gather(
        check_database_connection(db),
        check_redis_connection(redis),
    )

    is_ready = db_status == "up" and redis_status == "up"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "unhealthy",
        "components": {
            "database": db_status,
            "redis": redis_status,
        },
    }
