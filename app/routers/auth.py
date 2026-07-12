import httpx2
import json
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from redis.asyncio import Redis
from app.redis_client import get_redis

from app.database import get_db
from app.models import User, Role
from app.config import settings

# v1 版本的驗證路由, 包含 Discord OAuth2 登入流程和相關的 Redis 驗證碼管理
router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

# Discord API Endpoints
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"

@router.get("/discord/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def discord_login(response: Response):
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
    
    redirect_response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    redirect_response.set_cookie(
        key=settings.cookie_auth_login_state_name,
        value=state,
        max_age=settings.cookie_auth_login_state_max_age,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite   # type: ignore[arg-type]
    )
    
    return redirect_response

@router.get("/discord/callback")
async def discord_callback(request: Request, code: str, state: str, db: AsyncSession = Depends(get_db), redis: Redis = Depends(get_redis)):
    """
    處理 Discord OAuth2 回調, 驗證 state 並交換 access token
    """
    # 驗證 CSRF state
    stored_state = request.cookies.get(settings.cookie_auth_login_state_name)
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")
    
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
        token_response = await client.post(DISCORD_TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if token_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange code for token")
        
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No access token received")
        
        # 使用 access token 獲取用戶信息
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = await client.get(DISCORD_USER_URL, headers=headers)
        if user_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch user info")
        
        user_info = user_response.json()
    
    discord_id = user_info["id"]
    # username = user_info["username"]
    
    # 根據 discord_id 查詢或創建用戶, 並生成 session 存入 Redis
    query = select(User).where(User.discord_id == discord_id).options(selectinload(User.roles).selectinload(Role.permissions))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(discord_id=discord_id)
        role_query = select(Role).where(Role.name == "user").options(selectinload(Role.permissions))
        default_role = (await db.execute(role_query)).scalar_one_or_none()
        if default_role:
            user.roles.append(default_role)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        if default_role:
            user_permissions = list({permission.name for permission in default_role.permissions})
        else:
            user_permissions = []
    else:
        user_permissions = list({permission.name for role in user.roles for permission in role.permissions})
    
    session_token = secrets.token_urlsafe(32)  # 生成 session token
    
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.cookie_auth_name,
        value=session_token,
        max_age=settings.cookie_auth_max_age,
        path=settings.cookie_path,
        secure=settings.cookie_secure,
        httponly=settings.cookie_httponly,
        samesite=settings.cookie_samesite   # type: ignore[arg-type]
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
    }
    await redis.set(f"auth:session:{session_token}", json.dumps(session_data), ex=settings.cookie_auth_max_age)
    await redis.set(f"auth:permissions:{user.id}", json.dumps(user_permissions), ex=settings.cookie_auth_max_age)
    
    return response

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, redis: Redis = Depends(get_redis)):
    """
    處理用戶登出, 刪除 session cookie 和 Redis 中的 session
    """
    session_token = request.cookies.get(settings.cookie_auth_name)
    if session_token:
        session_key = f"auth:session:{session_token}"
        permissions_key = None

        session_raw = await redis.get(session_key)
        if session_raw:
            try:
                if isinstance(session_raw, bytes):
                    session_raw = session_raw.decode("utf-8")
                session_data = json.loads(session_raw)
                internal_user_id = session_data.get("internal_user_id")
                if internal_user_id is not None:
                    permissions_key = f"auth:permissions:{internal_user_id}"
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                permissions_key = None

        if permissions_key:
            await redis.delete(session_key, permissions_key)
        else:
            await redis.delete(session_key)
    
    response.delete_cookie(
        key=settings.cookie_auth_name,
        path=settings.cookie_path,
    )  # 刪除 session
    return