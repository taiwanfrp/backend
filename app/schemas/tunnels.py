from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime

from app.models import TunnelProtocol, TunnelStatus
from app.utils.validators import validate_host

from app.schemas.common import ErrorResponse
from app.schemas.nodes import NODE_NOT_FOUND_DOC


SUPPORTED_PROTOCOLS = {TunnelProtocol.TCP, TunnelProtocol.UDP}


class TunnelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    node_id: int = Field(..., ge=1, le=2147483647)
    protocol: TunnelProtocol = Field(
        ..., description="The protocol for the tunnel (TCP or UDP)"
    )
    local_ip: str = Field(default="127.0.0.1", max_length=50)
    local_port: int = Field(..., ge=1, le=65535)
    remote_port: Optional[int] = Field(None, ge=1, le=65535)

    is_kcp_enabled: bool = Field(default=True)
    is_proxy_protocol_v2_enabled: bool = Field(default=False)

    @field_validator("protocol")
    @classmethod
    def check_protocol_supported(cls, v: str) -> str:
        """
        檢查選擇的協定是否被支援
        """
        if v not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported protocol: {v}. Supported protocols are: {', '.join(sorted(p.value for p in SUPPORTED_PROTOCOLS))}"
            )
        return v

    @field_validator("local_ip")
    @classmethod
    def check_local_ip_valid(cls, v: str) -> str:
        """
        驗證 local_ip 是否為合法的 IP (包含私有 IP) 或網域
        """
        return validate_host(v, allow_private=True)


class TunnelUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    node_id: Optional[int] = Field(None, ge=1, le=2147483647)
    protocol: Optional[TunnelProtocol] = Field(
        None, description="The protocol for the tunnel (TCP or UDP)"
    )
    local_ip: Optional[str] = Field(None, max_length=50)
    local_port: Optional[int] = Field(None, ge=1, le=65535)
    remote_port: Optional[int] = Field(None, ge=1, le=65535)

    is_kcp_enabled: Optional[bool] = Field(None)
    is_proxy_protocol_v2_enabled: Optional[bool] = Field(None)
    is_enabled: Optional[bool] = Field(None)

    @field_validator("protocol")
    @classmethod
    def check_protocol_supported(cls, v: str) -> str:
        """
        檢查選擇的協定是否被支援
        """
        if v not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported protocol: {v}. Supported protocols are: {', '.join(sorted(p.value for p in SUPPORTED_PROTOCOLS))}"
            )
        return v

    @field_validator("local_ip")
    @classmethod
    def check_local_ip_valid(cls, v: str) -> str:
        """
        驗證 local_ip 是否為合法的 IP (包含私有 IP) 或網域
        """
        return validate_host(v, allow_private=True)


class TunnelResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    node_id: int
    protocol: TunnelProtocol
    local_ip: str
    local_port: int
    remote_port: Optional[int]
    is_kcp_enabled: bool
    is_proxy_protocol_v2_enabled: bool
    is_enabled: bool
    status: TunnelStatus
    token_prefix: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TunnelCreateResponse(TunnelResponse):
    agent_token: str = Field(
        ..., description="用於驗證 Agent 的身份, 由後端生成, 僅顯示一次"
    )


TUNNEL_NOT_FOUND_DOC = {
    404: {
        "model": ErrorResponse,
        "description": "Tunnel not found",
        "content": {"application/json": {"example": {"detail": "Tunnel not found"}}},
    }
}

TUNNEL_CREATE_DOC = {
    **NODE_NOT_FOUND_DOC,
    400: {
        "model": ErrorResponse,
        "description": "Invalid request data",
        "content": {
            "application/json": {
                "examples": {
                    "Node is not available": {
                        "summary": "Node is not available",
                        "value": {"detail": "Node is not available"},
                    },
                    "Remote port is missing for TCP and UDP protocols": {
                        "summary": "Remote port is missing for TCP and UDP protocols",
                        "value": {
                            "detail": "remote_port is required for TCP and UDP protocols"
                        },
                    },
                    "Remote port is out of range": {
                        "summary": "Remote port is out of range",
                        "value": {
                            "detail": "remote_port must be between <number> and <number>"
                        },
                    },
                    "Remote port is already in use": {
                        "summary": "Remote port is already in use",
                        "value": {
                            "detail": "remote_port is already in use on this node"
                        },
                    },
                }
            }
        },
    },
    403: {
        "model": ErrorResponse,
        "description": "Port has been reached the maximum limit",
        "content": {
            "application/json": {
                "example": {
                    "detail": "You have reached your maximum tunnel limit <number>"
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict with existing tunnel",
        "content": {
            "application/json": {
                "example": {
                    "detail": "A tunnel with the same configuration already exists"
                }
            }
        },
    },
}

TUNNEL_UPDATE_DOC = {
    **TUNNEL_NOT_FOUND_DOC,
    **NODE_NOT_FOUND_DOC,
    400: {
        "model": ErrorResponse,
        "description": "Invalid request data",
        "content": {
            "application/json": {
                "examples": {
                    "Node is not available": {
                        "summary": "Node is not available",
                        "value": {"detail": "Node is not available"},
                    },
                    "Remote port is missing for TCP and UDP protocols": {
                        "summary": "Remote port is missing for TCP and UDP protocols",
                        "value": {
                            "detail": "remote_port is required for TCP and UDP protocols"
                        },
                    },
                    "Remote port is out of range": {
                        "summary": "Remote port is out of range",
                        "value": {
                            "detail": "remote_port must be between <number> and <number>"
                        },
                    },
                }
            }
        },
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict with existing tunnel",
        "content": {
            "application/json": {
                "examples": {
                    "Remote port has been used": {
                        "summary": "Remote port is already in use",
                        "value": {
                            "detail": "remote_port is already in use on this node"
                        },
                    },
                    "Conflict with existing tunnel": {
                        "summary": "Tunnel with the same name already exists",
                        "value": {"detail": "Tunnel with the same name already exists"},
                    },
                }
            }
        },
    },
}

TUNNEL_DELETE_DOC = {
    **TUNNEL_NOT_FOUND_DOC,
}
