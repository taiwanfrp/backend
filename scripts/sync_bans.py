"""把資料庫裡封禁中的帳號寫入 Redis 的 auth:ban:{discord_id}, 給客服單 bot 查詢

平常由 API 在修改狀態時寫入, 只有第一次部署或 Redis 資料遺失時需要執行
"""

import asyncio
import sys
from pathlib import Path

import redis.asyncio as redis
from sqlalchemy import select

sys.path.append(str(Path(__file__).parent.parent))

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import AccountStatus, User
from app.utils.sessions import is_status_expired, sync_ban


async def sync_bans():
    client = redis.Redis.from_url(settings.redis_url)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.status == AccountStatus.BANNED)
        )
        users = [
            user
            for user in result.scalars().all()
            if not is_status_expired(user.status_until)
        ]
        for user in users:
            await sync_ban(client, user)
    await client.aclose()
    print(f"已寫入 {len(users)} 個封禁中的帳號")


if __name__ == "__main__":
    asyncio.run(sync_bans())
