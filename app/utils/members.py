import json
import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.models import User
from app.schemas.users import (
    DiscordMemberResponse,
    UserLimitsResponse,
    UserResponse,
)
from app.utils.sessions import user_limits

logger = logging.getLogger(__name__)


def member_key(discord_id: str) -> str:
    # 與客服單 bot 的約定, bot 每 10 分鐘寫入伺服器成員的名稱, TTL 1 小時
    return f"discord:member:{discord_id}"


async def get_members(
    redis: Redis, discord_ids: list[str]
) -> dict[str, DiscordMemberResponse | None]:
    """
    用 Discord ID 查詢伺服器成員, 不在伺服器, 格式不對或 Redis 讀取失敗時是 None
    """
    members: dict[str, DiscordMemberResponse | None] = dict.fromkeys(discord_ids)
    if not discord_ids:
        return members

    try:
        values = await redis.mget([member_key(i) for i in discord_ids])
    except RedisError:
        logger.warning("Failed to read Discord members from Redis", exc_info=True)
        return members

    for discord_id, value in zip(discord_ids, values, strict=True):
        if not value:
            continue
        try:
            members[discord_id] = DiscordMemberResponse.model_validate(
                json.loads(value)
            )
        except (ValueError, ValidationError):
            continue
    return members


async def to_user_responses(redis: Redis, users: list[User]) -> list[UserResponse]:
    """
    加上實際的資源上限與 Discord 伺服器成員, user.roles 必須已載入
    """
    members = await get_members(redis, [user.discord_id for user in users])
    return [
        UserResponse.model_validate(user).model_copy(
            update={
                "limits": UserLimitsResponse(**user_limits(user)),
                "member": members[user.discord_id],
            }
        )
        for user in users
    ]


async def to_user_response(redis: Redis, user: User) -> UserResponse:
    return (await to_user_responses(redis, [user]))[0]
