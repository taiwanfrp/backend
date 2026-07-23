from fastapi import APIRouter, Depends, HTTPException, status, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, RequirePermissions
from app.models import Role, Permission
from app.database import get_db
from app.limiter import limiter

from app.schemas.roles import (
    RoleCreateRequest,
    RoleResponse,
    ROLE_NOT_FOUND_DOC,
)

router = APIRouter(prefix="/api/v1/roles", tags=["Roles"])


@router.get("", response_model=list[RoleResponse])
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
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
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
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


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")  # type: ignore[arg-type]
@limiter.limit("40/hour")  # type: ignore[arg-type]
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
