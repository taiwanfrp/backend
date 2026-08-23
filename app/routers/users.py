from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis
from app.redis_client import get_redis

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

    # TODO: 更新 Redis 內的帳號狀態

    return
