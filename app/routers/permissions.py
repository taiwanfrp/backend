from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.dependencies import CurrentUser, RequirePermissions
from app.models import Permission
from app.database import get_db
from app.limiter import limiter

from app.schemas.roles import PermissionResponse

router = APIRouter(prefix="/api/v1/permissions", tags=["Permissions"])


@router.get("", response_model=list[PermissionResponse])
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def get_permissions(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(RequirePermissions(["role.read.all"])),
    db: AsyncSession = Depends(get_db),
):
    """
    取得系統中所有的權限節點列表, 需要 role.read.all 權限
    """
    stmt = select(Permission).order_by(Permission.id.asc())
    result = await db.execute(stmt)

    return result.scalars().all()
