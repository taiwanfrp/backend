from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentUser, RequirePermissions
from app.limiter import limiter
from app.models import Permission, Role, User, user_roles
from app.redis_client import get_redis
from app.schemas.roles import (
    ROLE_CREATE_DOC,
    ROLE_NOT_FOUND_DOC,
    ROLE_UPDATE_DOC,
    RoleCreateRequest,
    RoleResponse,
    RoleUpdateRequest,
)
from app.utils.sessions import sync_user_sessions

router = APIRouter(prefix="/api/v1/roles", tags=["Roles"])


async def get_role_user_ids(db: AsyncSession, role_id: int) -> list[str]:
    """
    取得擁有指定身份組的使用者 ID
    """
    stmt = select(user_roles.c.user_id).where(user_roles.c.role_id == role_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def sync_users_sessions(db: AsyncSession, redis: Redis, user_ids: list[str]):
    """
    身份組變更後, 將受影響使用者最新的權限與資源上限同步到所有登入 session
    """
    if not user_ids:
        return

    stmt = (
        select(User)
        .where(User.id.in_(user_ids))
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .execution_options(populate_existing=True)
    )
    result = await db.execute(stmt)
    for user in result.scalars().all():
        await sync_user_sessions(redis, user)


@router.get("", response_model=list[RoleResponse])
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_roles(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(RequirePermissions(["role.read.all"])),
    db: AsyncSession = Depends(get_db),
):
    """
    取得所有身份組的列表, 需要 role.read.all 權限
    包含身份組擁有的的權限節點
    """
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.id.asc())  # type: ignore[arg-type]
    result = await db.execute(stmt)

    return result.scalars().all()


@router.get("/{role_id}", response_model=RoleResponse, responses=ROLE_NOT_FOUND_DOC)  # type: ignore[arg-type]
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_role(
    request: Request,
    response: Response,
    role_id: int = Path(..., description="身份組 ID", ge=1, le=2147483647),
    current_user: CurrentUser = Depends(RequirePermissions(["role.read.all"])),
    db: AsyncSession = Depends(get_db),
):
    """
    取得單一身份組的詳細資訊, 需要 role.read.all 權限
    包含身份組擁有的的權限節點
    """
    stmt = (
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    return role


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ROLE_CREATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def create_role(
    request: Request,
    response: Response,
    payload: RoleCreateRequest,
    current_user: CurrentUser = Depends(RequirePermissions(["role.create"])),
    db: AsyncSession = Depends(get_db),
):
    """
    建立新的身份組, 需要 role.create 權限
    - 如果 permissions 傳入空陣列, 則身份組不會擁有任何權限節點
    """
    stmt = select(Role).where(Role.name == payload.name)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role with the same name already exists",
        )

    new_role = Role(
        name=payload.name,
        description=payload.description,
        max_tunnels=payload.max_tunnels,
        max_bandwidth=payload.max_bandwidth,
    )

    # 將權限節點加入身份組
    if payload.permissions:
        perm_stmt = select(Permission).where(Permission.id.in_(payload.permissions))
        perm_result = await db.execute(perm_stmt)
        permissions = list(perm_result.scalars().all())

        if len(permissions) != len(payload.permissions):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Some permissions not found",
            )

        new_role.permissions = permissions

    db.add(new_role)

    try:
        await db.commit()
        await db.refresh(new_role)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role with the same name already exists",
        )

    return new_role


@router.patch("/{role_id}", response_model=RoleResponse, responses=ROLE_UPDATE_DOC)  # type: ignore[arg-type]
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def update_role(
    request: Request,
    response: Response,
    payload: RoleUpdateRequest,
    role_id: int = Path(..., description="身份組 ID", ge=1, le=2147483647),
    current_user: CurrentUser = Depends(RequirePermissions(["role.update"])),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    更新身份組資訊, 需要 role.update 權限
    - 系統預設身份組 (admin, user, node_provider) 不允許改名
    - 如果 permissions 傳入空陣列, 則身份組不會擁有任何權限節點
    - 更新後會同步到擁有該身份組的使用者所有登入 session
    """
    stmt = (
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return role

    if "name" in update_data:
        if (
            role.name in ["admin", "user", "node_provider"]
            and update_data["name"] != role.name
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update system default roles",
            )
        if update_data["name"] != role.name:
            stmt = select(Role).where(Role.name == update_data["name"])
            result = await db.execute(stmt)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Role with the same name already exists",
                )
        role.name = update_data["name"]

    if "description" in update_data:
        role.description = update_data["description"]
    if "max_tunnels" in update_data:
        role.max_tunnels = update_data["max_tunnels"]
    if "max_bandwidth" in update_data:
        role.max_bandwidth = update_data["max_bandwidth"]

    if "permissions" in update_data:
        if not update_data["permissions"]:
            role.permissions = []
        else:
            perm_stmt = select(Permission).where(
                Permission.id.in_(update_data["permissions"])
            )
            perm_result = await db.execute(perm_stmt)
            permissions = list(perm_result.scalars().all())

            if len(permissions) != len(update_data["permissions"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Some permissions not found",
                )

            role.permissions = permissions

    try:
        await db.commit()
        await db.refresh(role)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role with the same name already exists",
        )

    await sync_users_sessions(db, redis, await get_role_user_ids(db, role_id))

    return role


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ROLE_NOT_FOUND_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def delete_role(
    request: Request,
    response: Response,
    role_id: int = Path(..., description="身份組 ID", ge=1, le=2147483647),
    current_user: CurrentUser = Depends(RequirePermissions(["role.delete"])),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除身份組, 需要 role.delete 權限
    - 系統預設身份組 (admin, user, node_provider) 無法被刪除
    - 刪除後會同步到原本擁有該身份組的使用者所有登入 session
    """
    stmt = select(Role).where(Role.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    if role.name in ["admin", "user", "node_provider"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system default roles",
        )

    user_ids = await get_role_user_ids(db, role_id)

    await db.delete(role)
    await db.commit()

    await sync_users_sessions(db, redis, user_ids)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
