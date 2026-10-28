import json

from redis.asyncio import Redis

from app.config import settings
from app.models import User


def calculate_limit(custom_limit: int | None, role_limits: list[int]) -> int:
    """
    計算使用者的資源上限, 自訂值優先, 否則取身份組中最大的值 (0 表示無限制)
    """
    if custom_limit is not None:
        return custom_limit
    if not role_limits or 0 in role_limits:
        return 0
    return max(role_limits)


async def sync_user_sessions(redis: Redis, user: User):
    """
    將使用者最新的狀態, 身份組, 權限與資源上限同步到所有登入 session
    - user.roles 與 role.permissions 必須已載入
    """
    user_permissions = list(
        {permission.name for role in user.roles for permission in role.permissions}
    )
    roles_list = [role.name for role in user.roles]
    limits = {
        "max_tunnels": calculate_limit(
            user.custom_max_tunnels, [role.max_tunnels for role in user.roles]
        ),
        "max_bandwidth": calculate_limit(
            user.custom_max_bandwidth, [role.max_bandwidth for role in user.roles]
        ),
    }

    await redis.set(
        f"auth:permissions:{user.id}",
        json.dumps(user_permissions),
        ex=settings.cookie_auth_max_age,
    )

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
            session_data["internal_account_status"] = user.status.value
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
