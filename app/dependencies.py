import json
from fastapi import Depends, HTTPException, status, Request, Response
from redis.asyncio import Redis
from app.redis_client import get_redis

# 定義一個 Pydantic 模型，用來提供 IDE 強型別支援
from pydantic import BaseModel

class CurrentUser(BaseModel):
    internal_user_id: str
    discord_id: str
    username: str
    avatar: str | None = None

async def get_current_user(request: Request, redis: Redis = Depends(get_redis)) -> CurrentUser:
    """
    從 Redis 中獲取當前用戶信息的依賴函數, 用於保護需要驗證的路由
    """
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user_data_json = await redis.get(f"auth:session:{session_token}")
    if not user_data_json:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    
    try:
        user_data = json.loads(user_data_json)
        await redis.expire(f"auth:session:{session_token}", 604800)  # 延長 session 有效期 7天
        return CurrentUser(**user_data)
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid session data") from e