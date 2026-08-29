from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import get_current_user, CurrentUser
from app.models import Permission
from app.database import get_db
from app.limiter import limiter

from app.schemas.roles import PermissionResponse

router = APIRouter(prefix="/api/v1/permissions", tags=["Permissions"])


@router.get("", response_model=list[PermissionResponse])
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_permissions(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    取得當前使用者擁有的權限節點列表
    """
    if not current_user.permissions:
        return []

    stmt = (
        select(Permission)
        .where(Permission.name.in_(current_user.permissions))
        .order_by(Permission.id.asc())
    )
    result = await db.execute(stmt)

    return result.scalars().all()
