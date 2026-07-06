from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, or_, and_
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.dependencies import get_optional_current_user, CurrentUser, RequirePermissions
from app.models import Node, NodeStatus, User
from app.database import get_db

router = APIRouter(prefix="/api/v1/nodes", tags=["Nodes"])

class NodeCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    host: str = Field(..., max_length=100)
    port_start: int = Field(..., ge=1, le=65535)
    port_end: int = Field(..., ge=1, le=65535)
    is_public: bool = True

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

    class Config:
        from_attributes = True

@router.get("", response_model=list[NodeResponse])
async def get_nodes(owner: Optional[str] = None, current_user: CurrentUser | None = Depends(get_optional_current_user), db: AsyncSession = Depends(get_db)):
    """
    獲取節點列表的路由, 根據使用者權限返回對應可見的節點列表
    - 未登入、一般使用者: 僅能看到 ACTIVE 且 is_public=True 的節點
    - 節點擁有者: 能看到自己擁有的所有節點
    - 管理員: 能看到所有節點
    """
    stmt = select(Node)
    is_admin = current_user and "node.read.all" in current_user.permissions
    
    if not is_admin:
        visible_statuses = [NodeStatus.ACTIVE, NodeStatus.MAINTENANCE, NodeStatus.DISABLED]
        public_condition = and_(Node.status.in_(visible_statuses), Node.is_public.is_(True))
        
        if current_user:
            stmt = stmt.where(
                or_(
                    public_condition,
                    Node.owner_id == current_user.internal_user_id,
                    Node.allowed_users.any(User.id == current_user.internal_user_id)
                )
            )
        else:
            stmt = stmt.where(public_condition)
    
    if owner:
        if owner.lower() == "me":
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
            stmt = stmt.where(Node.owner_id == current_user.internal_user_id)
        else:
            stmt = stmt.where(Node.owner_id == owner)
    
    stmt = stmt.order_by(Node.created_at.asc())
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(request: NodeCreateRequest, current_user: CurrentUser = Depends(RequirePermissions(["node.create"])), db: AsyncSession = Depends(get_db)):
    """
    建立新的 FRP 節點, 預設狀態為 DRAFT
    """
    if request.port_start > request.port_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="port_start must be less than or equal to port_end")
    
    new_node = Node(
        name=request.name,
        description=request.description,
        host=request.host,
        port_start=request.port_start,
        port_end=request.port_end,
        status=NodeStatus.DRAFT,
        is_public=request.is_public,
        owner_id=current_user.internal_user_id
    )
    
    db.add(new_node)
    try:
        await db.commit()
        await db.refresh(new_node)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Node with the same name or host already exists")

    return new_node