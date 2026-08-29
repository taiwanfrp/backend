from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis
from app.redis_client import get_redis
import json

from app.dependencies import get_current_user, CurrentUser, RequirePermissions
from app.database import get_db
from app.models import User, AccountStatus
from app.limiter import limiter

from app.schemas.users import (
    GET_CURRENT_USER_DOC,
)

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
