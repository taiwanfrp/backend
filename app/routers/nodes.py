from fastapi import APIRouter, Depends, HTTPException, status, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, or_, and_
from typing import Optional

from app.dependencies import get_optional_current_user, CurrentUser, RequirePermissions
from app.models import Node, NodeStatus, User
from app.database import get_db
from app.limiter import limiter

from app.schemas.nodes import (
    NodeCreateRequest,
    NodeUpdateRequest,
    NodeResponse,
    NODE_CREATE_DOC,
    NODE_UPDATE_DOC,
    NODE_DELETE_DOC,
    NODE_NOT_FOUND_DOC,
)

router = APIRouter(prefix="/api/v1/nodes", tags=["Nodes"])


@router.get("", response_model=list[NodeResponse])
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def get_nodes(
    request: Request,
    response: Response,
    owner: Optional[str] = None,
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    獲取節點列表的路由, 根據使用者權限返回對應可見的節點列表
    - 未登入、一般使用者: 僅能看到 ACTIVE 且 is_public=True 的節點
    - 節點擁有者: 能看到自己擁有的所有節點
    - 管理員: 能看到所有節點
    """
    stmt = select(Node)
    is_admin = current_user and "node.read.all" in current_user.permissions

    if not is_admin:
        visible_statuses = [
            NodeStatus.ACTIVE,
            NodeStatus.MAINTENANCE,
            NodeStatus.DISABLED,
        ]
        public_condition = and_(
            Node.status.in_(visible_statuses), Node.is_public.is_(True)
        )

        if current_user:
            stmt = stmt.where(
                or_(
                    public_condition,
                    Node.owner_id == current_user.internal_user_id,
                    Node.allowed_users.any(User.id == current_user.internal_user_id),
                )
            )
        else:
            stmt = stmt.where(public_condition)

    if owner:
        if owner.lower() == "me":
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
                )
            stmt = stmt.where(Node.owner_id == current_user.internal_user_id)
        else:
            stmt = stmt.where(Node.owner_id == owner)

    stmt = stmt.order_by(Node.created_at.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{node_id}", response_model=NodeResponse, responses=NODE_NOT_FOUND_DOC)  # type: ignore[arg-type]
@limiter.limit("60/minute")  # type: ignore[arg-type]
@limiter.limit("1000/hour")  # type: ignore[arg-type]
async def get_node(
    request: Request,
    response: Response,
    node_id: int = Path(..., description="Node ID", ge=1, le=2147483647),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    獲取單個節點的路由, 根據使用者權限返回對應可見的節點資訊
    - 未登入、一般使用者: 僅能看到 ACTIVE 且 is_public=True 的節點
    - 節點擁有者: 能看到自己擁有的所有節點
    - 管理員: 能看到所有節點
    若無權查看則返回 404 Not Found
    """
    stmt = select(Node).where(Node.id == node_id)
    is_admin = current_user and "node.read.all" in current_user.permissions

    if not is_admin:
        visible_statuses = [
            NodeStatus.ACTIVE,
            NodeStatus.MAINTENANCE,
            NodeStatus.DISABLED,
        ]
        public_condition = and_(
            Node.status.in_(visible_statuses), Node.is_public.is_(True)
        )

        if current_user:
            stmt = stmt.where(
                or_(
                    public_condition,
                    Node.owner_id == current_user.internal_user_id,
                    Node.allowed_users.any(User.id == current_user.internal_user_id),
                )
            )
        else:
            stmt = stmt.where(public_condition)

    result = await db.execute(stmt)
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )

    return node


@router.post(
    "",
    response_model=NodeResponse,
    status_code=status.HTTP_201_CREATED,
    responses=NODE_CREATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("3/hour")  # type: ignore[arg-type]
@limiter.limit("5/day")  # type: ignore[arg-type]
async def create_node(
    request: Request,
    response: Response,
    payload: NodeCreateRequest,
    current_user: CurrentUser = Depends(RequirePermissions(["node.create"])),
    db: AsyncSession = Depends(get_db),
):
    """
    建立新的 FRP 節點, 預設狀態為 DRAFT
    """
    if payload.port_start > payload.port_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="port_start must be less than or equal to port_end",
        )

    new_node = Node(
        name=payload.name,
        description=payload.description,
        host=payload.host,
        port_start=payload.port_start,
        port_end=payload.port_end,
        status=NodeStatus.DRAFT,
        is_public=payload.is_public,
        owner_id=current_user.internal_user_id,
    )

    db.add(new_node)
    try:
        await db.commit()
        await db.refresh(new_node)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node with the same name or host already exists",
        )

    return new_node


@router.patch("/{node_id}", response_model=NodeResponse, responses=NODE_UPDATE_DOC)  # type: ignore[arg-type]
@limiter.limit("5/hour")  # type: ignore[arg-type]
@limiter.limit("30/day")  # type: ignore[arg-type]
async def update_node(
    request: Request,
    response: Response,
    payload: NodeUpdateRequest,
    node_id: int = Path(..., description="Node ID", ge=1, le=2147483647),
    current_user: CurrentUser = Depends(RequirePermissions(["node.update.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    更新節點資訊的路由, 只有節點擁有者或管理員可以更新節點資訊
    """
    stmt = select(Node).where(Node.id == node_id)
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )

    is_admin = "node.update.all" in current_user.permissions
    if not is_admin and node.owner_id != current_user.internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this node",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return node  # No changes to apply

    new_port_start = update_data.get("port_start", node.port_start)
    new_port_end = update_data.get("port_end", node.port_end)
    if new_port_start > new_port_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="port_start must be less than or equal to port_end",
        )

    if not is_admin:
        current_status = node.status
        target_status = update_data.get("status")

        has_critical_change = (
            ("host" in update_data and update_data["host"] != node.host)
            or (
                "port_start" in update_data
                and update_data["port_start"] != node.port_start
            )
            or ("port_end" in update_data and update_data["port_end"] != node.port_end)
        )

        if has_critical_change:
            update_data["status"] = NodeStatus.DRAFT
            target_status = NodeStatus.DRAFT

        if target_status and target_status != current_status:
            if current_status in [NodeStatus.DRAFT, NodeStatus.REVIEWING]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot manually change status while node is in {current_status.value} state",
                )
            elif current_status in [
                NodeStatus.ACTIVE,
                NodeStatus.MAINTENANCE,
                NodeStatus.DISABLED,
            ]:
                pass

    for key, value in update_data.items():
        setattr(node, key, value)

    try:
        await db.commit()
        await db.refresh(node)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node with the same name or host already exists",
        )

    return node


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NODE_DELETE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("3/hour")  # type: ignore[arg-type]
@limiter.limit("5/day")  # type: ignore[arg-type]
async def delete_node(
    request: Request,
    response: Response,
    node_id: int = Path(..., description="Node ID", ge=1, le=2147483647),
    current_user: CurrentUser = Depends(RequirePermissions(["node.delete.own"])),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除節點的路由, 只有節點擁有者或管理員可以刪除節點
    """
    stmt = select(Node).where(Node.id == node_id)
    result = await db.execute(stmt)
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )

    is_admin = "node.delete.all" in current_user.permissions
    if not is_admin and node.owner_id != current_user.internal_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this node",
        )

    await db.delete(node)
    await db.commit()
