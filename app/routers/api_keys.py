from fastapi import APIRouter, Depends, HTTPException, status, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import select, and_, func
import hashlib

from app.utils.api_key import generate_api_key
from app.dependencies import get_current_user, CurrentUser
from app.models import ApiKey, Permission
from app.database import get_db
from app.config import settings
from app.limiter import limiter

from app.schemas.api_keys import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    API_KEY_CREATE_DOC,
    API_KEY_DELETE_DOC,
)

router = APIRouter(prefix="/api/v1/api-keys", tags=["API-Keys"])


@router.get("", response_model=list[ApiKeyResponse])
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_api_keys(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    列出當前使用者建立的所有 API Key
    """
    stmt = (
        select(ApiKey)
        .where(ApiKey.user_id == current_user.internal_user_id)
        .options(selectinload(ApiKey.permissions))
    )
    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    return [
        ApiKeyResponse(
            id=api_key.id,
            description=api_key.description,
            prefix=api_key.prefix,
            expires_at=api_key.expires_at,
            permission_ids=[permission.id for permission in api_key.permissions],
        )
        for api_key in api_keys
    ]


@router.get("/{api_key_id}", response_model=ApiKeyResponse)
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_api_key(
    request: Request,
    response: Response,
    api_key_id: str = Path(
        ..., min_length=36, max_length=36, description="API Key 的 UUID"
    ),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    取得指定的 API Key 資訊
    """
    stmt = (
        select(ApiKey)
        .where(
            and_(
                ApiKey.id == api_key_id, ApiKey.user_id == current_user.internal_user_id
            )
        )
        .options(selectinload(ApiKey.permissions))
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found"
        )

    return ApiKeyResponse(
        id=api_key.id,
        description=api_key.description,
        prefix=api_key.prefix,
        expires_at=api_key.expires_at,
        permission_ids=[permission.id for permission in api_key.permissions],
    )


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=API_KEY_CREATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def create_api_key(
    request: Request,
    response: Response,
    payload: ApiKeyCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    建立新的 API Key
    """
    # 檢查使用者是否已達到 API Key 上限
    count_stmt = select(func.count(ApiKey.id)).where(
        ApiKey.user_id == current_user.internal_user_id
    )
    count_result = await db.execute(count_stmt)
    current_key_count = count_result.scalar_one()

    if current_key_count >= settings.max_api_keys_per_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You have reached the maximum limit of {settings.max_api_keys_per_user} API Keys",
        )

    target_permissions = []
    if payload.permission_ids:
        stmt = select(Permission).where(Permission.id.in_(payload.permission_ids))
        result = await db.execute(stmt)
        target_permissions = list(result.scalars().all())

        if len(target_permissions) != len(set(payload.permission_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more permission IDs are invalid",
            )
        user_permission_names = set(current_user.permissions)
        for permission in target_permissions:
            if permission.name not in user_permission_names:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Cannot assign permission '{permission.name}' you don't have",
                )

    # 生成 API Key
    raw_api_key = generate_api_key()

    # 取得前綴 twf_live_12345678
    prefix = "_".join(raw_api_key.split("_")[:3])

    hashed_key = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()

    new_api_key = ApiKey(
        user_id=current_user.internal_user_id,
        description=payload.description,
        prefix=prefix,
        hashed_key=hashed_key,
        expires_at=payload.expires_at,
        permissions=target_permissions,
    )

    try:
        db.add(new_api_key)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API Key generation collision, please try again",
        )

    return ApiKeyCreateResponse(
        id=new_api_key.id,
        description=new_api_key.description,
        api_key=raw_api_key,
        expires_at=new_api_key.expires_at,
        permission_ids=[permission.id for permission in target_permissions],
    )


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=API_KEY_DELETE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def delete_api_key(
    request: Request,
    response: Response,
    api_key_id: str = Path(
        ..., min_length=36, max_length=36, description="API Key 的 UUID"
    ),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除指定的 API Key
    """
    stmt = select(ApiKey).where(
        and_(ApiKey.id == api_key_id, ApiKey.user_id == current_user.internal_user_id)
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found"
        )

    await db.delete(api_key)
    await db.commit()
