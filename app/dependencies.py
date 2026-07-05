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
    avatar: str | None
    mfa_enabled: bool
    locale: str
    email: str | None
    verified: bool
    permissions: list[str] = []

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
        
        if user_data.get("internal_account_status") not in ["active"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account is {user_data.get('internal_account_status')}")
        
        internal_user_id = user_data["internal_user_id"]
        
        permissions_json = await redis.get(f"auth:permissions:{internal_user_id}")
        permissions = json.loads(permissions_json) if permissions_json else []
        
        await redis.expire(f"auth:session:{session_token}", settings.cookie_auth_max_age)  # 延長 session 有效期
        if permissions_json:
            await redis.expire(f"auth:permissions:{internal_user_id}", settings.cookie_auth_max_age)  # 延長 permissions 有效期
        
        user_data["permissions"] = permissions
        return CurrentUser(**user_data)
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid session data") from e

class RequirePermissions:
    """
    權限驗證攔截器
    用法: Depends(RequirePermissions(["tunnel.read.own", "subdomain.create"]))
    """
    def __init__(self, required_permissions: list[str]):
        self.required_permissions = set(required_permissions)
    
    def __call__(self, current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_permissions = set(current_user.permissions)
        
        missing_permissions = self.required_permissions - user_permissions
        
        if missing_permissions:
            missing_list = sorted(list(missing_permissions))
            missing_str = ", ".join(f"'{permission}'" for permission in missing_list)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied. Missing permissions: [{missing_str}]")
        return current_user