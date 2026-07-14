import enum
from datetime import datetime, timezone
import uuid6

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Column,
    Table,
    Integer,
)
from app.database import Base


def generate_uuidv7() -> str:
    # Generate a UUIDv7 string
    return str(uuid6.uuid7())


def get_utc_now() -> datetime:
    # Get the current UTC time
    return datetime.now(timezone.utc)


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    BANNED = "banned"


class AuthMethodType(str, enum.Enum):
    TOTP = "totp"
    EMAIL = "email"
    U2F = "u2f"


class NodeStatus(str, enum.Enum):
    ACTIVE = "active"  # 可用
    DRAFT = "draft"  # 待審核(草稿)
    REVIEWING = "reviewing"  # 審核中
    MAINTENANCE = "maintenance"  # 維護中
    DISABLED = "disabled"  # 停用


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuidv7
    )
    discord_id: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )  # Discord ID 現在已經 19 位了, 預留到 20 位
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus), nullable=False, default=AccountStatus.SUSPENDED
    )
    custom_max_tunnels: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )  # 自訂最大隧道數量, None 表示使用角色的限制
    custom_max_bandwidth: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )  # 自訂最大頻寬限制, None 表示使用角色的限制
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    auth_methods: Mapped[list["UserAuthMethod"]] = relationship(
        "UserAuthMethod", back_populates="user", cascade="all, delete-orphan"
    )
    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="user_roles", back_populates="users"
    )
    nodes: Mapped[list["Node"]] = relationship(
        "Node", back_populates="owner", cascade="all, delete-orphan"
    )
    allowed_nodes: Mapped[list["Node"]] = relationship(
        "Node", secondary="node_guests", back_populates="allowed_users"
    )
    tunnels: Mapped[list["Tunnel"]] = relationship(
        "Tunnel", back_populates="owner", cascade="all, delete-orphan"
    )


class UserAuthMethod(Base):
    __tablename__ = "user_auth_methods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    method_type: Mapped[AuthMethodType] = mapped_column(
        Enum(AuthMethodType), nullable=False
    )
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    user: Mapped[User] = relationship("User", back_populates="auth_methods")


# permission

# role 與 permission 多對多中介表
role_permission = Table(
    "role_permission",
    Base.metadata,
    Column(
        "role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# user 與 role 多對多中介表
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )  # e.g., "tunnel.create"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary=role_permission, back_populates="permissions"
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )  # e.g., "admin"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_tunnels: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # 0 表示無限制
    max_bandwidth: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3
    )  # 0 表示無限制
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    permissions: Mapped[list[Permission]] = relationship(
        "Permission", secondary=role_permission, back_populates="roles"
    )
    users: Mapped[list["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )


# node

# 私有節點的受邀使用者多對多中介表
node_guests = Table(
    "node_guests",
    Base.metadata,
    Column(
        "node_id", Integer, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, default=get_utc_now),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    ),
)


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    port_start: Mapped[int] = mapped_column(Integer, nullable=False)
    port_end: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus), nullable=False, default=NodeStatus.DRAFT
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    owner: Mapped[User] = relationship("User", back_populates="nodes")
    allowed_users: Mapped[list[User]] = relationship(
        "User", secondary=node_guests, back_populates="allowed_nodes"
    )
    tunnels: Mapped[list["Tunnel"]] = relationship(
        "Tunnel", back_populates="node", cascade="all, delete-orphan"
    )


# tunnel
class TunnelProtocol(str, enum.Enum):
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"
    TCPMUX = "tcpmux"
    STCP = "stcp"
    SUDP = "sudp"


class TunnelStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Tunnel(Base):
    __tablename__ = "tunnels"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuidv7
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol: Mapped[TunnelProtocol] = mapped_column(
        Enum(TunnelProtocol), nullable=False, default=TunnelProtocol.TCP
    )
    local_ip: Mapped[str] = mapped_column(
        String(50), nullable=False, default="127.0.0.1"
    )
    local_port: Mapped[int] = mapped_column(Integer, nullable=False)
    remote_port: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # TCP/UDP 必填, HTTP/HTTPS 為 80/443, STCP/SUDP 為空
    custom_domain: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )  # HTTP/HTTPS 必填, 其他為空
    is_kcp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_proxy_protocol_v2_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[TunnelStatus] = mapped_column(
        Enum(TunnelStatus), nullable=False, default=TunnelStatus.ACTIVE
    )  # 僅管理員可修改
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_utc_now,
        onupdate=get_utc_now,
    )

    owner: Mapped[User] = relationship("User", back_populates="tunnels")
    node: Mapped[Node] = relationship("Node", back_populates="tunnels")
