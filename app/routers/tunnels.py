from fastapi import APIRouter, Depends, HTTPException, status, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, and_, func
import hashlib

from app.utils.tokens import generate_secure_token
from app.dependencies import CurrentUser, RequirePermissions
from app.models import Node, NodeStatus, Tunnel, TunnelProtocol, TunnelStatus
from app.database import get_db
from app.limiter import limiter

from app.schemas.tunnels import (
    TunnelCreateRequest,
    TunnelCreateResponse,
    TunnelUpdateRequest,
    TunnelResponse,
    TUNNEL_CREATE_DOC,
    TUNNEL_UPDATE_DOC,
    TUNNEL_DELETE_DOC,
    TUNNEL_NOT_FOUND_DOC,
)

router = APIRouter(prefix="/api/v1/tunnels", tags=["Tunnels"])


@router.get("", response_model=list[TunnelResponse])
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
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


@router.get(
    "/{tunnel_id}",
    response_model=TunnelResponse,
    responses=TUNNEL_NOT_FOUND_DOC,  # type: ignore[arg-type]
)
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
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


@router.post(
    "",
    response_model=TunnelCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=TUNNEL_CREATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
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
    if current_user.limits.max_tunnels and current_user.limits.max_tunnels > 0:
        count_stmt = select(func.count(Tunnel.id)).where(
            Tunnel.owner_id == current_user.internal_user_id
        )
        current_tunnel_count = await db.scalar(count_stmt) or 0

        if current_tunnel_count >= current_user.limits.max_tunnels:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You have reached your maximum tunnel limit {current_user.limits.max_tunnels}",
            )
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

    raw_agent_token = generate_secure_token(token_type="tunl")
    token_prefix = "_".join(raw_agent_token.split("_")[:3])
    token_hashed = hashlib.sha256(raw_agent_token.encode("utf-8")).hexdigest()

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
        token_prefix=token_prefix,
        token_hashed=token_hashed,
    )

    db.add(new_tunnel)
    try:
        await db.commit()
        await db.refresh(new_tunnel)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tunnel with the same configuration already exists",
        )

    tunnel_dict = TunnelResponse.model_validate(new_tunnel).model_dump()
    return TunnelCreateResponse(**tunnel_dict, agent_token=raw_agent_token)


@router.patch(
    "/{tunnel_id}",
    response_model=TunnelResponse,
    responses=TUNNEL_UPDATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def update_tunnel(
    request: Request,
    response: Response,
    tunnel_data: TunnelUpdateRequest,
    tunnel_id: str = Path(..., min_length=36, max_length=36, description="隧道的 UUID"),
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
            detail="Tunnel with the same name already exists",
        )

    return tunnel


@router.delete(
    "/{tunnel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=TUNNEL_DELETE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
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
