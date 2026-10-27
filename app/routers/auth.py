import json
import secrets

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, GetOptionalCurrentUser
from app.limiter import limiter
from app.models import Role, User
from app.redis_client import get_redis
from app.schemas.auth import (
    DISCORD_CALLBACK_DOC,
    TICKET_CODE_DOC,
    TicketCodeResponse,
)
from app.utils.tokens import hash_session_token

# v1 版本的驗證路由, 包含 Discord OAuth2 登入流程和相關的 Redis 驗證碼管理
router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

# Discord API Endpoints
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"

# 客服單 bot 的授權碼有效時間 (秒), 與 bot 的約定, 修改前要先通知對方
TICKET_CODE_MAX_AGE = 30

# 停權中的帳號也可以開客服單 (例如申請啟用帳號)
get_ticket_user = GetOptionalCurrentUser(allow_suspended=True)


@router.get("/discord/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def discord_login(request: Request, response: Response):
    """
    生成 Discord OAuth2 登入 URL 並重定向用戶, 同時產生並存儲 CSRF state 防止 CSRF 攻擊
    """
    state = secrets.token_urlsafe(16)  # 生成隨機 state 參數

    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": settings.discord_oauth2_scope,
        "state": state,
    }

    from urllib.parse import urlencode

    auth_url = f"{DISCORD_AUTH_URL}?{urlencode(params)}"

    redirect_response = RedirectResponse(
        url=auth_url, status_code=status.HTTP_302_FOUND
    )
    redirect_response.set_cookie(
        key=settings.cookie_auth_login_state_name,
        value=state,
        max_age=settings.cookie_auth_login_state_max_age,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )

    return redirect_response


@router.get("/discord/callback", responses=DISCORD_CALLBACK_DOC)  # type: ignore[arg-type]
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def discord_callback(
    request: Request,
    response: Response,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """
    處理 Discord OAuth2 回調, 驗證 state 並交換 access token
    """
    # 驗證 CSRF state
    stored_state = request.cookies.get(settings.cookie_auth_login_state_name)
    if not stored_state or stored_state != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state"
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code"
        )

    # 使用 code 交換 access token, 並從 Discord API 獲取用戶信息

    # 交換 access token
    data = {
        "client_id": settings.discord_client_id,
        "client_secret": settings.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.discord_redirect_uri,
    }

    async with httpx2.AsyncClient() as client:
        token_response = await client.post(
            DISCORD_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token",
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token received",
            )

        # 使用 access token 獲取用戶信息
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = await client.get(DISCORD_USER_URL, headers=headers)
        if user_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch user info",
            )

        user_info = user_response.json()

    discord_id = user_info["id"]
    # username = user_info["username"]

    # 根據 discord_id 查詢或創建用戶, 並生成 session 存入 Redis
    query = (
        select(User)
        .where(User.discord_id == discord_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        user = User(discord_id=discord_id)
        role_query = (
            select(Role)
            .where(Role.name == "user")
            .options(selectinload(Role.permissions))
        )
        default_role = (await db.execute(role_query)).scalar_one_or_none()
        if default_role:
            user.roles.append(default_role)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        if default_role:
            user_permissions = list(
                {permission.name for permission in default_role.permissions}
            )
            roles_list = [default_role.name]
            tunnels_limit = default_role.max_tunnels
            bandwidth_limit = default_role.max_bandwidth
        else:
            user_permissions = []
            roles_list = []
            tunnels_limit = 0
            bandwidth_limit = 0
    else:
        user_permissions = list(
            {permission.name for role in user.roles for permission in role.permissions}
        )

        roles_list = [role.name for role in user.roles]

        if user.custom_max_tunnels is not None:
            tunnels_limit = user.custom_max_tunnels
        else:
            tunnels_limits = [role.max_tunnels for role in user.roles]
            tunnels_limit = (
                0
                if (not tunnels_limits or 0 in tunnels_limits)
                else max(tunnels_limits)
            )

        if user.custom_max_bandwidth is not None:
            bandwidth_limit = user.custom_max_bandwidth
        else:
            bandwidth_limits = [role.max_bandwidth for role in user.roles]
            bandwidth_limit = (
                0
                if (not bandwidth_limits or 0 in bandwidth_limits)
                else max(bandwidth_limits)
            )

    session_token = secrets.token_urlsafe(32)  # 生成 session token
    # Redis 只存 session token 的雜湊, 外洩時拿不到能用的 cookie
    session_key = hash_session_token(session_token)

    response = RedirectResponse(
        url=settings.site_url, status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key=settings.cookie_auth_name,
        value=session_token,
        max_age=settings.cookie_auth_max_age,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )
    response.delete_cookie(
        key=settings.cookie_auth_login_state_name,
        path=settings.cookie_path,
    )  # 刪除 state cookie

    # 在 Redis 中存儲驗證碼或用戶信息, 以便後續驗證使用
    # 要把整個 user_info 存進去, 以便後續取得 email 等資料
    session_data = {
        "internal_user_id": user.id,
        "internal_account_status": user.status.value,
        "discord_id": user.discord_id,
        "username": user_info.get("username", "Unknown"),
        "avatar": user_info.get("avatar"),
        "mfa_enabled": user_info.get("mfa_enabled", False),
        "locale": user_info.get("locale", "en-US"),
        "email": user_info.get("email"),
        "verified": user_info.get("verified", False),
        "roles": roles_list,
        "limits": {
            "max_tunnels": tunnels_limit,
            "max_bandwidth": bandwidth_limit,
        },
    }
    await redis.set(
        f"auth:session:{session_key}",
        json.dumps(session_data),
        ex=settings.cookie_auth_max_age,
    )
    await redis.set(
        f"auth:permissions:{user.id}",
        json.dumps(user_permissions),
        ex=settings.cookie_auth_max_age,
    )

    await redis.sadd(f"auth:user_sessions:{user.id}", session_key)
    await redis.expire(f"auth:user_sessions:{user.id}", settings.cookie_auth_max_age)

    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def logout(
    request: Request, response: Response, redis: Redis = Depends(get_redis)
):
    """
    處理用戶登出, 刪除 session cookie 和 Redis 中的 session
    """
    session_token = request.cookies.get(settings.cookie_auth_name)
    if session_token:
        await redis.delete(f"auth:session:{hash_session_token(session_token)}")

    response.delete_cookie(
        key=settings.cookie_auth_name,
        path=settings.cookie_path,
    )  # 刪除 session


@router.post(
    "/ticket-code",
    response_model=TicketCodeResponse,
    responses=TICKET_CODE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("600/hour")  # type: ignore[arg-type]
async def create_ticket_code(
    request: Request,
    response: Response,
    current_user: CurrentUser | None = Depends(get_ticket_user),
    redis: Redis = Depends(get_redis),
):
    """
    產生客服單 bot 的一次性授權碼, 前端拿去跟 bot 交換 bot 自己的 session cookie
    - 只接受 session cookie, 不接受 API Key
    - 授權碼只存 session token 的雜湊, bot 不會拿到能登入的 session
    - 只能使用一次 (bot 用 GETDEL 取出), 30 秒後過期
    """
    # 只允許前端呼叫, 避免其他網站在背景取得授權碼
    origin = request.headers.get("origin")
    if origin not in settings.cors_origins.split(","):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed"
        )

    session_token = request.cookies.get(settings.cookie_auth_name)
    if not current_user or not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    code = secrets.token_urlsafe(32)
    await redis.set(
        f"auth:ticket_code:{code}",
        hash_session_token(session_token),
        ex=TICKET_CODE_MAX_AGE,
    )

    return TicketCodeResponse(code=code)
