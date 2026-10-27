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
