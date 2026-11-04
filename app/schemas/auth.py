from pydantic import BaseModel, Field

from app.schemas.common import ErrorResponse

# Discord callback
DISCORD_CALLBACK_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_oauth_state": {
                        "summary": "Invalid or missing OAuth state",
                        "value": {"detail": "Invalid OAuth state"},
                    },
                    "missing_authorization_code": {
                        "summary": "Missing authorization code",
                        "value": {"detail": "Missing authorization code"},
                    },
                    "failed_token_exchange": {
                        "summary": "Failed token exchange",
                        "value": {"detail": "Failed to exchange code for token"},
                    },
                    "no_access_token": {
                        "summary": "No access token",
                        "value": {"detail": "No access token received"},
                    },
                    "failed_user_info_fetch": {
                        "summary": "Failed user info fetch",
                        "value": {"detail": "Failed to fetch user info"},
                    },
                }
            }
        },
    }
}


# 客服單 bot 的授權碼
class TicketCodeResponse(BaseModel):
    code: str = Field(
        ..., description="一次性授權碼, 30 秒內拿去跟客服單 bot 交換 session"
    )


TICKET_CODE_DOC = {
    401: {
        "model": ErrorResponse,
        "description": "Not authenticated",
        "content": {
            "application/json": {
                "examples": {
                    "not_authenticated": {
                        "summary": "Cookie missing, session expired or account cannot be used",
                        "value": {"detail": "Not authenticated"},
                    },
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Origin not allowed",
        "content": {
            "application/json": {
                "examples": {
                    "origin_not_allowed": {
                        "summary": "Request is not from the frontend",
                        "value": {"detail": "Origin not allowed"},
                    },
                }
            }
        },
    },
}


# 登入中的裝置
class SessionResponse(BaseModel):
    session_id: str | None = Field(
        ..., description="用來登出這個裝置, 這個功能上線前登入的 session 為 null"
    )
    created_at: str | None = Field(..., description="登入時間 (ISO 8601, UTC)")
    ip: str | None = Field(..., description="登入時的 IP")
    user_agent: str | None = Field(..., description="登入時的 User-Agent")
    current: bool = Field(..., description="是否為目前的裝置")


_NOT_AUTHENTICATED = {
    "model": ErrorResponse,
    "description": "Not authenticated",
    "content": {
        "application/json": {
            "examples": {
                "not_authenticated": {
                    "summary": "Cookie missing, session expired or account cannot be used",
                    "value": {"detail": "Not authenticated"},
                },
            }
        }
    },
}

GET_SESSIONS_DOC = {401: _NOT_AUTHENTICATED}

DELETE_SESSION_DOC = {
    401: _NOT_AUTHENTICATED,
    404: {
        "model": ErrorResponse,
        "description": "Session not found",
        "content": {
            "application/json": {
                "examples": {
                    "session_not_found": {
                        "summary": "Session does not exist, expired or belongs to another user",
                        "value": {"detail": "Session not found"},
                    },
                }
            }
        },
    },
}

# 登出所有裝置
DELETE_SESSIONS_DOC = {401: _NOT_AUTHENTICATED}
