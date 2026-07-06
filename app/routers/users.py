from fastapi import APIRouter, Depends
from app.dependencies import get_current_user, CurrentUser

router = APIRouter(prefix="/api/v1/users", tags=["Users"])

@router.get("/me", response_model=CurrentUser)
async def read_current_user(current_user: CurrentUser = Depends(get_current_user)):
    """
    獲取當前用戶信息的路由, 需要驗證
    """
    return current_user