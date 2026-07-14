from fastapi import APIRouter, Depends, HTTPException, status, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, and_
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime

from app.utils.validators import validate_host
from app.dependencies import CurrentUser, RequirePermissions
from app.models import Node, NodeStatus, Tunnel, TunnelProtocol, TunnelStatus
from app.database import get_db
from app.limiter import limiter

router = APIRouter(prefix="/api/v1/tunnels", tags=["Tunnels"])

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
                f"Unsupported protocol: {v}. Supported protocols are: {', '.join(SUPPORTED_PROTOCOLS)}"
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

    is_kcp_enabled: Optional[bool]
    is_proxy_protocol_v2_enabled: Optional[bool]
    is_enabled: Optional[bool]

    @field_validator("protocol")
    @classmethod
    def check_protocol_supported(cls, v: str) -> str:
        """
        檢查選擇的協定是否被支援
        """
        if v not in SUPPORTED_PROTOCOLS:
            raise ValueError(
                f"Unsupported protocol: {v}. Supported protocols are: {', '.join(SUPPORTED_PROTOCOLS)}"
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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[TunnelResponse])
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def get_tunnels(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(RequirePermissions(["tunnel.read.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    列出當前使用者建立的所有隧道
    """
    stmt = select(Tunnel).where(Tunnel.owner_id == current_user.internal_user_id)
    result = await db.execute(stmt)

    return result.scalars().all()


@router.get("/{tunnel_id}", response_model=TunnelResponse)
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def get_tunnel(
    request: Request,
    response: Response,
    tunnel_id: str = Path(..., min_length=36, max_length=36, description="隧道的 UUID"),
    current_user: CurrentUser = Depends(RequirePermissions(["tunnel.read.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    取得指定的隧道資訊
    """
    stmt = select(Tunnel).where(
        and_(Tunnel.id == tunnel_id, Tunnel.owner_id == current_user.internal_user_id)
    )
    result = await db.execute(stmt)
    tunnel = result.scalar_one_or_none()

    if not tunnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found"
        )

    return tunnel


@router.post("", response_model=TunnelResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")  # type: ignore[arg-type]
@limiter.limit("10/day")  # type: ignore[arg-type]
async def create_tunnel(
    request: Request,
    response: Response,
    tunnel_data: TunnelCreateRequest,
    current_user: CurrentUser = Depends(RequirePermissions(["tunnel.create"])),
    db: AsyncSession = Depends(get_db),
):
    """
    建立新的 FRP 隧道
    """
    result = await db.execute(select(Node).where(Node.id == tunnel_data.node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )
    if node.status != NodeStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Node is not available"
        )

    # 檢查 remote_port 是否位於 node 的可用範圍內
    if tunnel_data.protocol in {TunnelProtocol.TCP, TunnelProtocol.UDP}:
        if not tunnel_data.remote_port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="remote_port is required for TCP and UDP protocols",
            )
        if not (node.port_start <= tunnel_data.remote_port <= node.port_end):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"remote_port must be between {node.port_start} and {node.port_end}",
            )

    # 檢查同一個 node 上是否已經存在相同的 remote_port
    if tunnel_data.remote_port:
        result = await db.execute(
            select(Tunnel).where(
                and_(
                    Tunnel.node_id == tunnel_data.node_id,
                    Tunnel.remote_port == tunnel_data.remote_port,
                )
            )
        )
        existing_tunnel = result.scalar_one_or_none()
        if existing_tunnel:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="remote_port is already in use on this node",
            )

    new_tunnel = Tunnel(
        name=tunnel_data.name,
        description=tunnel_data.description,
        owner_id=current_user.internal_user_id,
        node_id=tunnel_data.node_id,
        protocol=tunnel_data.protocol,
        local_ip=tunnel_data.local_ip,
        local_port=tunnel_data.local_port,
        remote_port=tunnel_data.remote_port,
        is_kcp_enabled=tunnel_data.is_kcp_enabled,
        is_proxy_protocol_v2_enabled=tunnel_data.is_proxy_protocol_v2_enabled,
        is_enabled=True,
        status=TunnelStatus.ACTIVE,
    )

    db.add(new_tunnel)
    try:
        await db.commit()
        await db.refresh(new_tunnel)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tunnel with the same already exists",
        )

    return new_tunnel


@router.patch("/{tunnel_id}", response_model=TunnelResponse)
@limiter.limit("5/hour")  # type: ignore[arg-type]
@limiter.limit("10/day")  # type: ignore[arg-type]
async def update_tunnel(
    request: Request,
    response: Response,
    tunnel_id: str = Path(..., min_length=36, max_length=36, description="隧道的 UUID"),
    tunnel_data: TunnelUpdateRequest = Depends(),
    current_user: CurrentUser = Depends(RequirePermissions(["tunnel.update.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    更新指定的隧道資訊
    """
    stmt = select(Tunnel).where(
        and_(Tunnel.id == tunnel_id, Tunnel.owner_id == current_user.internal_user_id)
    )
    result = await db.execute(stmt)
    tunnel = result.scalar_one_or_none()

    if not tunnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found"
        )

    update_data = tunnel_data.model_dump(exclude_unset=True)
    if not update_data:
        return tunnel  # 沒有任何更新就直接回傳

    target_node_id = update_data.get("node_id", tunnel.node_id)
    target_protocol = update_data.get("protocol", tunnel.protocol)
    target_remote_port = update_data.get("remote_port", tunnel.remote_port)

    node_result = await db.execute(select(Node).where(Node.id == target_node_id))
    node = node_result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )
    if node.status != NodeStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Node is not available"
        )

    # 驗證 remote_port 是否位於 node 的可用範圍內
    if target_protocol in {TunnelProtocol.TCP, TunnelProtocol.UDP}:
        if not target_remote_port:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="remote_port is required for TCP and UDP protocols",
            )
        if not (node.port_start <= target_remote_port <= node.port_end):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"remote_port must be between {node.port_start} and {node.port_end}",
            )

    # 檢查 port 是否已經被使用
    if target_remote_port:
        port_check_stmt = select(Tunnel).where(
            and_(
                Tunnel.node_id == target_node_id,
                Tunnel.remote_port == target_remote_port,
                Tunnel.id != tunnel.id,  # 排除自己
            )
        )
        port_check_result = await db.execute(port_check_stmt)
        if port_check_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="remote_port is already in use on this node",
            )

    # 更新隧道資訊
    for field, value in update_data.items():
        setattr(tunnel, field, value)

    try:
        await db.commit()
        await db.refresh(tunnel)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tunnel with the same already exists",
        )

    return tunnel


@router.delete("/{tunnel_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")  # type: ignore[arg-type]
@limiter.limit("10/day")  # type: ignore[arg-type]
async def delete_tunnel(
    request: Request,
    response: Response,
    tunnel_id: str = Path(..., min_length=36, max_length=36, description="隧道的 UUID"),
    current_user: CurrentUser = Depends(RequirePermissions(["tunnel.delete.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除指定的隧道
    """
    stmt = select(Tunnel).where(
        and_(Tunnel.id == tunnel_id, Tunnel.owner_id == current_user.internal_user_id)
    )
    result = await db.execute(stmt)
    tunnel = result.scalar_one_or_none()

    if not tunnel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tunnel not found"
        )

    await db.delete(tunnel)
    await db.commit()
