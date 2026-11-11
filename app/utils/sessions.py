import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import AccountStatus, Role, User

# 停權, 封禁中的帳號只能登入與開客服單, 其他 API 只接受 active
LOGIN_ALLOWED_STATUSES = (
    AccountStatus.ACTIVE.value,
    AccountStatus.SUSPENDED.value,
    AccountStatus.BANNED.value,
)


def calculate_limit(custom_limit: int | None, role_limits: list[int]) -> int:
    """
    計算使用者的資源上限, 自訂值優先, 否則取身份組中最大的值 (0 表示無限制)
    """
    if custom_limit is not None:
        return custom_limit
    if not role_limits or 0 in role_limits:
        return 0
    return max(role_limits)


def user_limits(user: User) -> dict:
    """
    實際的資源上限, 自訂值優先, 否則依身份組計算
    - user.roles 必須已載入
    """
    return {
        "max_tunnels": calculate_limit(
            user.custom_max_tunnels, [role.max_tunnels for role in user.roles]
        ),
        "max_bandwidth": calculate_limit(
            user.custom_max_bandwidth, [role.max_bandwidth for role in user.roles]
        ),
    }


def as_utc(value: datetime) -> datetime:
    # MySQL 讀回來的時間沒有時區, 存的一律是 UTC
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def status_fields(user: User) -> dict:
    """
    session 與 /users/me 的停權, 封禁資訊
    """
    return {
        "internal_account_status": user.status.value,
        "status_reason": user.status_reason,
        "status_until": as_utc(user.status_until).isoformat()
        if user.status_until
        else None,
    }


def ban_key(discord_id: str) -> str:
    # 與客服單 bot 的約定, 從 Discord 開單的人不一定有 session, bot 用 Discord ID 查詢
    return f"auth:ban:{discord_id}"


async def sync_ban(redis: Redis, user: User):
    """
    封禁中的帳號寫入 auth:ban:{discord_id}, 有期限的在到期時自動過期, 其他狀態刪除
    """
    key = ban_key(user.discord_id)
    if user.status != AccountStatus.BANNED:
        await redis.delete(key)
        return

    value = json.dumps(
        {
            "reason": user.status_reason,
            "until": status_fields(user)["status_until"],
        }
    )
    if user.status_until:
        await redis.set(key, value, exat=int(as_utc(user.status_until).timestamp()))
    else:
        await redis.set(key, value)


async def sync_user_sessions(redis: Redis, user: User):
    """
    將使用者最新的狀態, 身份組, 權限與資源上限同步到所有登入 session 與 auth:ban
    - user.roles 與 role.permissions 必須已載入
    """
    user_permissions = list(
        {permission.name for role in user.roles for permission in role.permissions}
    )
    roles_list = [role.name for role in user.roles]
    limits = user_limits(user)

    await redis.set(
        f"auth:permissions:{user.id}",
        json.dumps(user_permissions),
        ex=settings.cookie_auth_max_age,
    )
    await sync_ban(redis, user)

    session_tokens = await redis.smembers(f"auth:user_sessions:{user.id}")
    for raw_token in session_tokens:
        token = (
            raw_token.decode("utf-8")
            if isinstance(raw_token, bytes)
            else str(raw_token)
        )

        session_json = await redis.get(f"auth:session:{token}")
        if session_json:
            session_data = json.loads(session_json)
            session_data.update(status_fields(user))
            session_data["roles"] = roles_list
            session_data["limits"] = limits

            ttl = await redis.ttl(f"auth:session:{token}")
            if ttl > 0:
                await redis.set(
                    f"auth:session:{token}",
                    json.dumps(session_data),
                    ex=ttl,
                )
        else:
            await redis.srem(f"auth:user_sessions:{user.id}", token)


def is_status_expired(status_until: datetime | str | None) -> bool:
    if not status_until:
        return False
    if isinstance(status_until, str):
        status_until = datetime.fromisoformat(status_until)
    return as_utc(status_until) <= datetime.now(UTC)


async def lift_expired_status(db: AsyncSession, redis: Redis, user: User) -> bool:
    """
    停權, 封禁到期時改回 active 並同步所有 session, 有改變時回傳 True
    - 沒有排程工作, 在登入與驗證身分時檢查
    - user.roles 與 role.permissions 必須已載入
    """
    if user.status not in (AccountStatus.SUSPENDED, AccountStatus.BANNED):
        return False
    if not is_status_expired(user.status_until):
        return False

    user.status = AccountStatus.ACTIVE
    user.status_reason = None
    user.status_until = None
    await db.commit()
    await sync_user_sessions(redis, user)
    return True


async def refresh_session_status(
    db: AsyncSession, redis: Redis, user_data: dict
) -> dict:
    """
    session 裡的停權, 封禁已經到期時, 從資料庫解除並回傳更新後的 session 資料
    """
    if user_data.get("internal_account_status") == AccountStatus.ACTIVE.value:
        return user_data
    if not is_status_expired(user_data.get("status_until")):
        return user_data

    stmt = (
        select(User)
        .where(User.id == user_data["internal_user_id"])
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user and await lift_expired_status(db, redis, user):
        return {**user_data, **status_fields(user)}
    return user_data
