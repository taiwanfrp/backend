from app.schemas.common import ErrorResponse


# Get current user
GET_CURRENT_USER_DOC = {
    401: {
        "model": ErrorResponse,
        "description": "Not authenticated",
        "content": {
            "application/json": {
                "examples": {
                    "cookie_missing": {
                        "summary": "Cookie missing",
                        "value": {"detail": "Not authenticated"},
                    },
                    "session_invalid": {
                        "summary": "Session expired or invalid",
                        "value": {"detail": "Session expired or invalid"},
                    },
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Account cannot be used",
        "content": {
            "application/json": {
                "examples": {
                    "account_suspended": {
                        "summary": "Account not active",
                        "value": {"detail": "Account is suspended"},
                    },
                    "account_deleted": {
                        "summary": "Account has been deleted",
                        "value": {"detail": "Account is deleted"},
                    },
                    "account_banned": {
                        "summary": "Account is banned",
                        "value": {"detail": "Account is banned"},
                    },
                }
            }
        },
    },
}
