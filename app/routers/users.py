import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, RequirePermissions, get_current_user
from app.limiter import limiter
from app.models import AccountStatus, Role, User
from app.redis_client import get_redis
from app.schemas.users import (
    GET_CURRENT_USER_DOC,
)

NODE_PROVIDER_ROLE_NAME = "node_provider"

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me", response_model=CurrentUser, responses=GET_CURRENT_USER_DOC)  # type: ignore[arg-type]
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def read_current_user(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    獲取當前用戶信息的路由, 需要驗證
    """
    return current_user


@router.post(
    "/{discord_id}/activate",
    dependencies=[Depends(RequirePermissions(["user.activate"]))],
)
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/day")  # type: ignore[arg-type]
async def activate_user(
    discord_id: str,
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    啟用帳號
    """
    stmt = select(User).where(User.discord_id == discord_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with Discord ID not found",
        )

    if user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User account is already active",
        )

    user.status = AccountStatus.ACTIVE
    await db.commit()

    session_tokens = await redis.smembers(f"auth:user_sessions:{user.id}")

    for raw_token in session_tokens:
        token = (
            raw_token.decode("utf-8")
            if isinstance(raw_token, bytes)
            else str(raw_token)
        )

        session_json = await redis.get(f"auth:session:{token}")
        if session_json:
            user_data = json.loads(session_json)
            user_data["internal_user_status"] = AccountStatus.ACTIVE.value

            ttl = await redis.ttl(f"auth:session:{token}")
            if ttl > 0:
                await redis.set(
                    f"auth:session:{token}",
                    json.dumps(user_data),
                    ex=ttl,
                )
        else:
            await redis.srem(f"auth:user_sessions:{user.id}", token)

    return {
        "message": f"User {discord_id} activated successfully",
        "status": AccountStatus.ACTIVE.value,
    }


@router.post(
    "/me/become-node-provider",
    dependencies=[Depends(RequirePermissions(["user.update.own"]))],
)
@limiter.limit("10/hour")  # type: ignore[arg-type]
@limiter.limit("30/day")  # type: ignore[arg-type]
async def become_node_provider(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    使用者自助取得節點提供者資格 (node_provider 身分組), 使其獲得 node.create 權限
    """
    stmt = (
        select(User)
        .where(User.id == current_user.internal_user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if any(role.name == NODE_PROVIDER_ROLE_NAME for role in user.roles):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a node provider",
        )

    role_stmt = (
        select(Role)
        .where(Role.name == NODE_PROVIDER_ROLE_NAME)
        .options(selectinload(Role.permissions))
    )
    node_provider_role = (await db.execute(role_stmt)).scalar_one_or_none()

    if not node_provider_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="node_provider role is not seeded",
        )

    user.roles.append(node_provider_role)
    await db.commit()
    await db.refresh(user)

    user_permissions = list(
        {permission.name for role in user.roles for permission in role.permissions}
    )

    permissions_json = json.dumps(user_permissions)
    await redis.set(
        f"auth:permissions:{user.id}",
        permissions_json,
        ex=settings.cookie_auth_max_age,
    )

    session_tokens = await redis.smembers(f"auth:user_sessions:{user.id}")
    for raw_token in session_tokens:
        token = (
            raw_token.decode("utf-8")
            if isinstance(raw_token, bytes)
            else str(raw_token)
        )

        session_json = await redis.get(f"auth:session:{token}")
        if session_json:
            session_data = json.loads(session_json)
            session_data["roles"] = [role.name for role in user.roles]

            ttl = await redis.ttl(f"auth:session:{token}")
            if ttl > 0:
                await redis.set(
                    f"auth:session:{token}",
                    json.dumps(session_data),
                    ex=ttl,
                )
        else:
            await redis.srem(f"auth:user_sessions:{user.id}", token)

    return {
        "message": "Successfully became a node provider",
        "roles": [role.name for role in user.roles],
        "permissions": user_permissions,
    }
