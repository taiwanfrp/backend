from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.config import settings

class AuthException(HTTPException):
    """
    用於處理驗證相關異常的自定義類別
    """
    pass

async def auth_exception_handler(request, exc: AuthException):
    """
    處理 Auth 接口的 Error Handler, 當傳入的 session cookie 無效則刪除 auth cookie
    """
    
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
    response.delete_cookie(
        key=settings.cookie_auth_name,
        path=settings.cookie_path,
        domain=settings.cookie_domain
    )
    return response