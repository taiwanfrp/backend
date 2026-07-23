from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

from app.schemas.permissions import PermissionResponse
from app.schemas.common import ErrorResponse


class RoleCreateRequest(BaseModel):
    name: str = Field(..., description="身份組名稱", min_length=1, max_length=50)
    description: Optional[str] = Field(None, description="身份組描述", max_length=255)
    max_tunnels: int = Field(..., description="最大允許的隧道數量", ge=0)
    max_bandwidth: int = Field(..., description="最大允許的頻寬 (Mbps)", ge=0)
    permissions: list[int] = Field(
        default_factory=list,
        description="身份組擁有的權限節點 ID 列表",
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
