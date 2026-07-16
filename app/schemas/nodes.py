from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime

from app.models import NodeStatus

from app.utils.validators import validate_host
from app.schemas.common import ErrorResponse


# 建立節點
class NodeCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    host: str = Field(..., max_length=100)
    port_start: int = Field(..., ge=1, le=65535)
    port_end: int = Field(..., ge=1, le=65535)
    is_public: bool = True

    @field_validator("host")
    @classmethod
    def check_host(cls, v: str) -> str:
        """
        驗證 host 是否為合法的公開 IP 或網域
        """
        return validate_host(v)


# 更新節點
class NodeUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    host: Optional[str] = Field(None, max_length=100)
    port_start: Optional[int] = Field(None, ge=1, le=65535)
    port_end: Optional[int] = Field(None, ge=1, le=65535)
    status: Optional[NodeStatus]
    is_public: Optional[bool]

    @field_validator("host")
    @classmethod
    def check_host(cls, v: str | None) -> Optional[str]:
        """
        驗證 host 是否為合法的公開 IP 或網域
        """
        if v is not None:
            return validate_host(v)
        return v


class NodeResponse(BaseModel):
    id: int
    name: str
    description: str | None
    host: str
    port_start: int
    port_end: int
    status: NodeStatus
    is_public: bool
    owner_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


NODE_NOT_FOUND_DOC = {
    404: {
        "model": ErrorResponse,
        "description": "Node not found",
        "content": {"application/json": {"example": {"detail": "Node not found"}}},
    }
}

NODE_CREATE_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "Invalid port range",
        "content": {
            "application/json": {
                "example": {
                    "detail": "port_start must be less than or equal to port_end"
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict",
        "content": {
            "application/json": {
                "example": {"detail": "Node with the same name or host already exists"}
            }
        },
    },
}

NODE_UPDATE_DOC = {
    **NODE_NOT_FOUND_DOC,
    400: {
        "model": ErrorResponse,
        "description": "Invalid update request",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_port": {
                        "summary": "Invalid port range",
                        "value": {
                            "detail": "port_start must be less than or equal to port_end"
                        },
                    },
                    "invalid_status_draft": {
                        "summary": "Cannot manually change status (Draft)",
                        "value": {
                            "detail": "Cannot manually change status while node is in draft state"
                        },
                    },
                    "invalid_status_reviewing": {
                        "summary": "Cannot manually change status (Reviewing)",
                        "value": {
                            "detail": "Cannot manually change status while node is in reviewing state"
                        },
                    },
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "No authorized",
        "content": {
            "application/json": {
                "example": {"detail": "Not authorized to update this node"}
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict",
        "content": {
            "application/json": {
                "example": {"detail": "Node with the same name or host already exists"}
            }
        },
    },
}

NODE_DELETE_DOC = {
    **NODE_NOT_FOUND_DOC,
    403: {
        "model": ErrorResponse,
        "description": "No authorized",
        "content": {
            "application/json": {
                "example": {"detail": "Not authorized to delete this node"}
            }
        },
    },
}
