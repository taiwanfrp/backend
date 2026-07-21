from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings


class RequestInfoMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)  # 執行請求處理鏈
        response.headers["X-SERVER-NAME"] = settings.server_id
        return response
