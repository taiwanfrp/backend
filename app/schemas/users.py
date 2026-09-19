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

# Become node provider
BECOME_NODE_PROVIDER_DOC = {
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
    404: {
        "model": ErrorResponse,
        "description": "User not found",
        "content": {
            "application/json": {
                "examples": {
                    "user_not_found": {
                        "summary": "User not found",
                        "value": {"detail": "User not found"},
                    },
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "User is already a node provider",
        "content": {
            "application/json": {
                "examples": {
                    "already_node_provider": {
                        "summary": "Already a node provider",
                        "value": {"detail": "User is already a node provider"},
                    },
                }
            }
        },
    },
}
