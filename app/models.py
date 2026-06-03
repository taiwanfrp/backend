import enum
from datetime import datetime, timezone
import uuid6

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, Enum, ForeignKey
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

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuidv7)
    discord_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)    # Discord ID 現在已經 19 位了, 預留到 20 位
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), nullable=False, default=AccountStatus.SUSPENDED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)

    auth_methods: Mapped[list["UserAuthMethod"]] = relationship("UserAuthMethod", back_populates="user", cascade="all, delete-orphan")

class UserAuthMethod(Base):
    __tablename__ = "user_auth_methods"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    method_type: Mapped[AuthMethodType] = mapped_column(Enum(AuthMethodType), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=get_utc_now, onupdate=get_utc_now)
    
    user: Mapped[User] = relationship("User", back_populates="auth_methods")