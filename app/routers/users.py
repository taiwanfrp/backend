from fastapi import APIRouter, Depends, Request, Response
from app.dependencies import get_current_user, CurrentUser

from app.limiter import limiter

from app.schemas.users import (
    GET_CURRENT_USER_DOC,
)

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("/me", response_model=CurrentUser, responses=GET_CURRENT_USER_DOC)  # type: ignore[arg-type]
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def read_current_user(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    獲取當前用戶信息的路由, 需要驗證
    """
    return current_user
