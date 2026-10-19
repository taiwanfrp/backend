from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import AccountStatus
from app.schemas.common import ErrorResponse


# 建立使用者
class UserCreateRequest(BaseModel):
    discord_id: str = Field(
        ..., description="使用者的 Discord ID", pattern=r"^\d{17,20}$"
    )
    status: AccountStatus = Field(
        default=AccountStatus.SUSPENDED, description="帳號狀態"
    )
    custom_max_tunnels: int | None = Field(
        None, description="自訂最大隧道數量, null 表示使用身份組的限制", ge=0
    )
    custom_max_bandwidth: int | None = Field(
        None, description="自訂最大頻寬 (Mbps), null 表示使用身份組的限制", ge=0
    )
    role_ids: list[int] | None = Field(
        None,
        description="身份組 ID 列表, 未傳入時預設給予 user 身份組, 傳入時需要 role.assign 權限",
    )


# 更新使用者
class UserUpdateRequest(BaseModel):
    status: AccountStatus | None = Field(None, description="帳號狀態")
    custom_max_tunnels: int | None = Field(
        None, description="自訂最大隧道數量, null 表示使用身份組的限制", ge=0
    )
    custom_max_bandwidth: int | None = Field(
        None, description="自訂最大頻寬 (Mbps), null 表示使用身份組的限制", ge=0
    )
    role_ids: list[int] | None = Field(
        None,
        description="身份組 ID 列表, 會取代使用者現有的身份組, 需要 role.assign 權限",
    )

    @field_validator("status", "role_ids")
    @classmethod
    def check_not_null(cls, v):
        """
        status 與 role_ids 不允許傳入 null
        """
        if v is None:
            raise ValueError("Field cannot be null")
        return v


class UserRoleResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: str
    discord_id: str
    status: AccountStatus
    custom_max_tunnels: int | None
    custom_max_bandwidth: int | None
    roles: list[UserRoleResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ROLES_NOT_FOUND_EXAMPLE = {
    "summary": "Some roles not found",
    "value": {"detail": "Some roles not found"},
}

ROLE_ASSIGN_DENIED_EXAMPLE = {
    "summary": "Missing role.assign permission",
    "value": {"detail": "Permission denied. Missing permissions: ['role.assign']"},
}

# Create user
USER_CREATE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Roles not found",
        "content": {
            "application/json": {
                "examples": {"roles_not_found": ROLES_NOT_FOUND_EXAMPLE}
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Permission denied",
        "content": {
            "application/json": {
                "examples": {"role_assign_denied": ROLE_ASSIGN_DENIED_EXAMPLE}
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "User already exists",
        "content": {
            "application/json": {
                "examples": {
                    "user_exists": {
                        "summary": "User already exists",
                        "value": {"detail": "User with Discord ID already exists"},
                    },
                }
            }
        },
    },
}

# Update user
USER_UPDATE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Invalid request",
        "content": {
            "application/json": {
                "examples": {
                    "update_self": {
                        "summary": "Cannot change own status or roles",
                        "value": {"detail": "Cannot change your own status or roles"},
                    },
                    "roles_not_found": ROLES_NOT_FOUND_EXAMPLE,
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Permission denied",
        "content": {
            "application/json": {
                "examples": {"role_assign_denied": ROLE_ASSIGN_DENIED_EXAMPLE}
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
                        "value": {"detail": "User with Discord ID not found"},
                    },
                }
            }
        },
    },
}

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

# Get user
USER_NOT_FOUND_DOC = {
    404: {
        "model": ErrorResponse,
        "description": "User not found",
        "content": {"application/json": {"example": {"detail": "User not found"}}},
    }
}

# Delete user
USER_DELETE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Cannot delete yourself",
        "content": {
            "application/json": {
                "examples": {
                    "delete_self": {
                        "summary": "Cannot delete yourself",
                        "value": {"detail": "Cannot delete your own account"},
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
                        "value": {"detail": "User with Discord ID not found"},
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
