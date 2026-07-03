import json
from fastapi import Depends, HTTPException, status, Request, Response
from redis.asyncio import Redis
from app.redis_client import get_redis
from app.config import settings

# 定義一個 Pydantic 模型，用來提供 IDE 強型別支援
from pydantic import BaseModel

from app.exception_handlers import AuthException

class CurrentUser(BaseModel):
    internal_user_id: str
    internal_account_status: str
    discord_id: str
    username: str
    avatar: str
    mfa_enabled: bool
    locale: str
    email: str
    verified: bool

async def get_current_user(request: Request, redis: Redis = Depends(get_redis)) -> CurrentUser:
    """
    從 Redis 中獲取當前用戶信息的依賴函數, 用於保護需要驗證的路由
    """
    session_token = request.cookies.get(settings.cookie_auth_name)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user_data_json = await redis.get(f"auth:session:{session_token}")
    if not user_data_json:
        raise AuthException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")  # 刪除無效 session cookie
    
    try:
        user_data = json.loads(user_data_json)
        await redis.expire(f"auth:session:{session_token}", settings.cookie_auth_max_age)  # 延長 session 有效期
        return CurrentUser(**user_data)
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid session data") from e