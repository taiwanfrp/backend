import asyncio
import sys
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload

sys.path.append(str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.models import User, Role


def draw_table(uuid: str, discord_id: str, is_admin: bool):
    admin_str = "Yes" if is_admin else "No"

    print("+----------+--------------------------------------+")
    print("| Field    | Value                                |")
    print("+----------+--------------------------------------+")
    print(f"| UUID     | {uuid:<36} |")
    print(f"| Discord  | {discord_id:<36} |")
    print(f"| Admin    | {admin_str:<36} |")
    print("+----------+--------------------------------------+")


async def make_admin():
    is_admin_input = input("是否要將使用者設為管理員? (yes/no): ").strip().lower()
    if is_admin_input not in ["yes", "y"]:
        print("\n已取消操作。")
        return

    discord_id = input("請輸入 Discord ID: ").strip()

    if not discord_id.isdigit():
        print("\n無效的 Discord ID, 請輸入有效的數字")
        return

    async with AsyncSessionLocal() as session:
        # 檢查是否已經存在管理員角色
        result = await session.execute(select(Role).where(Role.name == "admin"))
        admin_role = result.scalar_one_or_none()

        if not admin_role:
            print(
                "\n找不到 admin 身份組, 請先執行 uv run python scripts/seed_db.py 來初始化資料庫"
            )
            return

        user_result = await session.execute(
            select(User)
            .where(User.discord_id == discord_id)
            .options(selectinload(User.roles))
        )
        user = user_result.scalar_one_or_none()

        if not user:
            print(f"\n找不到 Discord ID 為 {discord_id} 的使用者")
            print("請先讓該使用者登入一次系統, 以便建立使用者資料")
            return

        if any(role.name == "admin" for role in user.roles):
            print(f"\nDiscord ID 為 {discord_id} 的使用者已經是管理員")
            return

        user.roles.append(admin_role)
        await session.commit()
        await session.refresh(user)

        print(f"\n已將 Discord ID 為 {discord_id} 的使用者設為管理員")
        print("\n")
        draw_table(user.id, user.discord_id, True)


if __name__ == "__main__":
    try:
        asyncio.run(make_admin())
    except KeyboardInterrupt:
        print("\n已起消操作")
