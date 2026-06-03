import redis.asyncio as redis
from app.config import settings

redis_pool = redis.ConnectionPool(
    host=settings.redis_host,
    port=settings.redis_port,
    username=settings.redis_user if settings.redis_user else None,
    password=settings.redis_password if settings.redis_password else None,
    db=settings.redis_db,
    decode_responses=True,
    max_connections=50,
)

async def get_redis():
    """
    提供給 FastAPI Depends 注入使用的產生器
    """
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()