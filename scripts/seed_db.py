import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.append(str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.models import Permission, Role

INITIAL_PERMISSIONS = [
    # 節點權限
    {"name": "node.create", "description": "建立新的節點"},
    {"name": "node.read.public", "description": "查看公開可用的節點"},
    {"name": "node.read.own", "description": "查看自己提供的節點"},
    {"name": "node.read.all", "description": "查看所有狀態全部的節點"},
    {"name": "node.update.own", "description": "編輯自己的節點資訊"},
    {"name": "node.update.all", "description": "編輯任意節點的資訊"},
    {"name": "node.delete.own", "description": "刪除自己提供的節點"},
    {"name": "node.delete.all", "description": "刪除任意節點"},
    # 身分組權限
    {"name": "role.create", "description": "建立新的身分組"},
    {"name": "role.read.own", "description": "查看目前使用者的身分組資訊"},
    {"name": "role.read.all", "description": "查看所有身分組資訊"},
    {"name": "role.update", "description": "編輯任意身分組"},
    {"name": "role.delete", "description": "刪除任意身分組"},
    {"name": "role.assign", "description": "將任意身分組賦予給使用者"},
    # 子網域權限
    {"name": "subdomain.create", "description": "建立新的子網域"},
    {"name": "subdomain.read.own", "description": "查看自己的子網域"},
    {"name": "subdomain.read.all", "description": "查看系統所有的子網域"},
    {"name": "subdomain.update.own", "description": "編輯自己的子網域"},
    {"name": "subdomain.update.all", "description": "編輯任意使用者的子網域"},
    {"name": "subdomain.delete.own", "description": "刪除自己的子網域"},
    {"name": "subdomain.delete.all", "description": "刪除任意使用者的子網域"},
    # 隧道權限
    {"name": "tunnel.create", "description": "建立新的隧道"},
    {"name": "tunnel.read.own", "description": "查看自己的隧道"},
    {"name": "tunnel.read.all", "description": "查看系統所有的隧道"},
    {"name": "tunnel.update.own", "description": "編輯自己的隧道"},
    {"name": "tunnel.update.all", "description": "編輯任意使用者的隧道"},
    {"name": "tunnel.delete.own", "description": "刪除自己的隧道"},
    {"name": "tunnel.delete.all", "description": "刪除任意使用者的隧道"},
    # 使用者權限
    {"name": "user.read.own", "description": "查看自己的使用者資訊"},
    {"name": "user.read.all", "description": "查看全部的使用者"},
    {"name": "user.update.own", "description": "編輯自己的使用者資訊"},
    {"name": "user.update.all", "description": "編輯任意使用者的資訊"},
    {"name": "user.delete.own", "description": "刪除自己的使用者帳號"},
    {"name": "user.delete.all", "description": "刪除任意使用者的帳號"},
]


async def seed():
    async with AsyncSessionLocal() as session:
        print("開始初始化資料庫預設資料...")

        # 寫入 Permissions
        for perm_data in INITIAL_PERMISSIONS:
            result = await session.execute(
                select(Permission).where(Permission.name == perm_data["name"])
            )
            perm = result.scalar_one_or_none()

            if not perm:
                new_perm = Permission(
                    name=perm_data["name"], description=perm_data["description"]
                )
                session.add(new_perm)
                print(f"[新增] 權限節點: {perm_data['name']}")

        await session.commit()

        # 建立預設身分組
        # 將資料庫內所有權限存入 Dict
        all_perms_result = await session.execute(select(Permission))
        all_perms = {p.name: p for p in all_perms_result.scalars().all()}

        # 建立預設使用者身分組 (user)
        user_role_result = await session.execute(
            select(Role).where(Role.name == "user")
        )
        user_role = user_role_result.scalar_one_or_none()

        if not user_role:
            user_role = Role(
                name="user", description="一般使用者", max_tunnels=3, max_bandwidth=3
            )
            base_perms = [
                "node.read.public",
                "role.read.own",
                "subdomain.create",
                "subdomain.read.own",
                "subdomain.update.own",
                "subdomain.delete.own",
                "tunnel.create",
                "tunnel.read.own",
                "tunnel.update.own",
                "tunnel.delete.own",
                "user.read.own",
                "user.update.own",
                "user.delete.own",
            ]
            user_role.permissions = [
                all_perms[name] for name in base_perms if name in all_perms
            ]
            session.add(user_role)
            print("[新增] 預設身分組: user")

        # 建立預設管理員身分組 (admin)
        admin_role_result = await session.execute(
            select(Role).where(Role.name == "admin")
        )
        admin_role = admin_role_result.scalar_one_or_none()

        if not admin_role:
            admin_role = Role(
                name="admin",
                description="系統管理員",
                max_tunnels=0,  # 0 表示無限制
                max_bandwidth=0,  # 0 表示無限制
            )
            # 管理員擁有全部權限
            admin_role.permissions = list(all_perms.values())
            session.add(admin_role)
            print("[新增] 預設身分組: admin")

        await session.commit()
        print("資料庫初始化/更新完成！")


if __name__ == "__main__":
    asyncio.run(seed())
