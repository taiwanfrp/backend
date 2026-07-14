from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10/second", "300/minute", "7200/hour", "28800/day"],
    storage_uri=settings.redis_url,
    headers_enabled=True,
    in_memory_fallback_enabled=True,
)
