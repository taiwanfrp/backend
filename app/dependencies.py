import json
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from redis.asyncio import Redis
from app.redis_client import get_redis
from app.database import get_db
from app.config import settings
from datetime import datetime, timezone
import hashlib

# 定義一個 Pydantic 模型，用來提供 IDE 強型別支援
from pydantic import BaseModel, Field
from typing import Optional

from app.exception_handlers import AuthException
from app.models import ApiKey, User


class UserLimits(BaseModel):
    max_tunnels: Optional[int] = Field(
        default=0, description="最大隧道數量限制, 0 代表無限制"
    )
    max_bandwidth: Optional[int] = Field(
        default=0, description="最大頻寬限制, 0 代表無限制"
    )


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
    roles: list[str] = Field(default_factory=list, description="使用者擁有的身份組名稱")
    permissions: list[str] = Field(
        default_factory=list, description="使用者擁有的所有權限節點"
    )
    limits: UserLimits = Field(
        default_factory=UserLimits, description="使用者擁有的資源上限"
    )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> CurrentUser:
    """
    從 Redis 中獲取當前用戶信息的依賴函數, 用於保護需要驗證的路由
    - Prioritizing API Key over session cookie
    """
    # API Key
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        api_key = auth_header.split(" ")[1]

        # 驗證 API Key 格式
        if api_key.startswith("twf_"):
            prefix = "_".join(api_key.split("_")[:3])
            hashed_key = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

            stmt = (
                select(ApiKey)
                .where(ApiKey.prefix == prefix, ApiKey.hashed_key == hashed_key)
                .options(
                    selectinload(ApiKey.user).selectinload(User.roles),
                    selectinload(ApiKey.permissions),
                )
            )
            result = await db.execute(stmt)
            api_key_obj = result.scalar_one_or_none()

            # api key 是否存在
            if not api_key_obj:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API Key",
                )

            # api key 是否過期
            if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(
                timezone.utc
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API Key has expired",
                )

            # 檢查所屬使用者帳號狀態
            db_user = api_key_obj.user
            if db_user.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account is {db_user.status}",
                )

            key_permissions = [
                permission.name for permission in api_key_obj.permissions
            ]

            max_tunnels = max([r.max_tunnels for r in db_user.roles], default=0)
            max_bandwidth = max([r.max_bandwidth for r in db_user.roles], default=0)

            return CurrentUser(
                internal_user_id=db_user.id,
                internal_account_status=db_user.status,
                discord_id=db_user.discord_id,
                username=f"API_User_{db_user.discord_id}",  # 資料僅在使用者以 Discord OAuth 登入時才有
                avatar=None,
                mfa_enabled=False,
                locale="en-US",
                email=None,
                verified=True,
                roles=[role.name for role in db_user.roles],
                permissions=key_permissions,
                limits=UserLimits(max_tunnels=max_tunnels, max_bandwidth=max_bandwidth),
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key format",
            )

    # Cookie
    session_token = request.cookies.get(settings.cookie_auth_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    user_data_json = await redis.get(f"auth:session:{session_token}")
    if not user_data_json:
        raise AuthException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )  # 刪除無效 session cookie

    try:
        user_data = json.loads(user_data_json)

        if user_data.get("internal_account_status") not in ["active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is {user_data.get('internal_account_status')}",
            )

        internal_user_id = user_data["internal_user_id"]

        permissions_json = await redis.get(f"auth:permissions:{internal_user_id}")
        permissions = json.loads(permissions_json) if permissions_json else []

        await redis.expire(
            f"auth:session:{session_token}", settings.cookie_auth_max_age
        )  # 延長 session 有效期
        if permissions_json:
            await redis.expire(
                f"auth:permissions:{internal_user_id}", settings.cookie_auth_max_age
            )  # 延長 permissions 有效期

        user_data["permissions"] = permissions
        return CurrentUser(**user_data)
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid session data",
        ) from e


class GetOptionalCurrentUser:
    def __init__(self, allow_suspended: bool = False):
        self.allow_suspended = allow_suspended

    async def __call__(
        self, request: Request, redis: Redis = Depends(get_redis)
    ) -> CurrentUser | None:
        """
        可選用戶驗證依賴函數
        若有合法的 session cookie, 則返回 CurrentUser, 否則返回 None
        不會拋出 HTTPException 401
        """
        session_token = request.cookies.get(settings.cookie_auth_name)
        if not session_token:
            return None

        user_data_json = await redis.get(f"auth:session:{session_token}")
        if not user_data_json:
            return None

        try:
            user_data = json.loads(user_data_json)

            allowed_statuses = (
                ["active", "suspended"] if self.allow_suspended else ["active"]
            )
            if user_data.get("internal_account_status") not in allowed_statuses:
                return None

            internal_user_id = user_data["internal_user_id"]

            permissions_json = await redis.get(f"auth:permissions:{internal_user_id}")
            permissions = json.loads(permissions_json) if permissions_json else []

            await redis.expire(
                f"auth:session:{session_token}", settings.cookie_auth_max_age
            )  # 延長 session 有效期
            if permissions_json:
                await redis.expire(
                    f"auth:permissions:{internal_user_id}", settings.cookie_auth_max_age
                )  # 延長 permissions 有效期

            user_data["permissions"] = permissions
            return CurrentUser(**user_data)
        except (json.JSONDecodeError, KeyError):
            return None


get_optional_current_user = GetOptionalCurrentUser(allow_suspended=False)


class RequirePermissions:
    """
    權限驗證攔截器
    用法: Depends(RequirePermissions(["tunnel.read.own", "subdomain.create"]))
    """

    def __init__(self, required_permissions: list[str]):
        self.required_permissions = set(required_permissions)

    def __call__(
        self, current_user: CurrentUser = Depends(get_current_user)
    ) -> CurrentUser:
        user_permissions = set(current_user.permissions)

        missing_permissions = self.required_permissions - user_permissions

        if missing_permissions:
            missing_list = sorted(list(missing_permissions))
            missing_str = ", ".join(f"'{permission}'" for permission in missing_list)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Missing permissions: [{missing_str}]",
            )
        return current_user
