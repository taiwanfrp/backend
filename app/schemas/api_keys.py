from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.schemas.common import ErrorResponse


# 建立 API Key
class ApiKeyCreateRequest(BaseModel):
    description: str = Field(
        ..., description="API Key 的用途描述", min_length=1, max_length=255
    )
    expires_at: Optional[datetime] = Field(
        default=None, description="API Key 的過期時間, 若為 None 則表示不過期"
    )
    permission_ids: list[int] = Field(
        default_factory=list, description="API Key 的權限 ID 列表 (可選)"
    )


# 建立 API Key 回應
class ApiKeyCreateResponse(BaseModel):
    id: str = Field(..., description="API Key 的唯一識別 ID")
    description: str = Field(..., description="API Key 的用途描述")
    api_key: str = Field(..., description="新建立的 API Key")
    expires_at: Optional[datetime] = Field(
        default=None, description="API Key 的過期時間, 若為 None 則表示不過期"
    )
    permission_ids: list[int] = Field(
        default_factory=list, description="API Key 的權限 ID 列表 (可選)"
    )


class ApiKeyResponse(BaseModel):
    id: str = Field(..., description="API Key 的唯一識別 ID")
    description: str = Field(..., description="API Key 的用途描述")
    prefix: str = Field(..., description="API Key 的前綴, 例如 twf_live_12345678")
    expires_at: Optional[datetime] = Field(
        default=None, description="API Key 的過期時間, 若為 None 則表示不過期"
    )
    permission_ids: list[int] = Field(
        default_factory=list, description="API Key 的權限 ID 列表 (可選)"
    )


API_KEY_NOT_FOUND_DOC = {
    404: {
        "model": ErrorResponse,
        "description": "API Key not found",
        "content": {"application/json": {"example": {"detail": "API Key not found"}}},
    }
}

API_KEY_CREATE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Bad Request",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_permission_ids": {
                        "summary": "Invalid permission IDs",
                        "value": {"detail": "One or more permission IDs are invalid"},
                    },
                    "api_key_limit_exceeded": {
                        "summary": "API Key limit exceeded",
                        "value": {
                            "detail": "You have reached the maximum limit of <number> API Keys"
                        },
                    },
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Cannot assign permission you don't have",
        "content": {
            "application/json": {
                "example": {
                    "detail": "Cannot assign permission '<permission_name>' you don't have"
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "API Key generation collision",
        "content": {
            "application/json": {
                "example": {"detail": "API Key generation collision, please try again"}
            }
        },
    },
}

API_KEY_DELETE_DOC = {
    **API_KEY_NOT_FOUND_DOC,
}
