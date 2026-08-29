from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

from app.schemas.permissions import PermissionResponse
from app.schemas.common import ErrorResponse


# 建立身份組
class RoleCreateRequest(BaseModel):
    name: str = Field(..., description="身份組名稱", min_length=1, max_length=50)
    description: Optional[str] = Field(None, description="身份組描述", max_length=255)
    max_tunnels: int = Field(..., description="最大允許的隧道數量", ge=0)
    max_bandwidth: int = Field(..., description="最大允許的頻寬 (Mbps)", ge=0)
    permissions: list[int] = Field(
        default_factory=list,
        description="身份組擁有的權限節點 ID 列表, 傳入空陣列表示身份組不會擁有任何權限節點",
    )


# 更新身份組
class RoleUpdateRequest(BaseModel):
    name: Optional[str] = Field(
        None, description="身份組名稱", min_length=1, max_length=50
    )
    description: Optional[str] = Field(None, description="身份組描述", max_length=255)
    max_tunnels: Optional[int] = Field(None, description="最大允許的隧道數量", ge=0)
    max_bandwidth: Optional[int] = Field(
        None, description="最大允許的頻寬 (Mbps)", ge=0
    )
    permissions: Optional[list[int]] = Field(
        default=None,
        description="身份組擁有的權限節點 ID 列表, 傳入空陣列表示身份組不會擁有任何權限節點",
    )


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None
    max_tunnels: int
    max_bandwidth: int
    permissions: list[PermissionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ROLE_NOT_FOUND_DOC = {
    404: {
        "model": ErrorResponse,
        "description": "Role not found",
        "content": {"application/json": {"example": {"detail": "Role not found"}}},
    }
}

ROLE_CREATE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Permissions not found",
        "content": {
            "application/json": {"example": {"detail": "Some permissions not found"}}
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict",
        "content": {
            "application/json": {
                "example": {"detail": "Role with the same name already exists"}
            }
        },
    },
}

ROLE_UPDATE_DOC = {
    **ROLE_NOT_FOUND_DOC,
    400: {
        "model": ErrorResponse,
        "description": "Permissions not found",
        "content": {
            "application/json": {"example": {"detail": "Some permissions not found"}}
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Forbidden",
        "content": {
            "application/json": {
                "example": {"detail": "Cannot update system default roles"}
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict",
        "content": {
            "application/json": {
                "example": {"detail": "Role with the same name already exists"}
            }
        },
    },
}
