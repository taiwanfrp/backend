import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.append(str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.models import AccountStatus, Role, User

DATA_PATH = Path("users.json")
FAILED_PATH = Path("users_failed.json")
MANUAL_PATH = Path("users_manual.json")

# 舊資料因歷史原因 3MB/s 有 3072 與 3096 兩種寫法
LEGACY_3MB_VALUES = {3072, 3096}


async def import_users(
    legacy_users: dict[str, dict],
) -> tuple[dict[str, dict], dict[str, dict]] | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Role).where(Role.name == "user"))
        user_role = result.scalar_one_or_none()

        if not user_role:
            print(
                "找不到 user 身份組, 請先執行 uv run python scripts/seed_db.py 來初始化資料庫"
            )
            return None

        existing_result = await session.execute(select(User.discord_id))
        existing_ids = set(existing_result.scalars().all())

        imported = 0
        failed: dict[str, dict] = {}
        manual: dict[str, dict] = {}

        for username, data in legacy_users.items():
            discord_id = str(data.get("discordUserId", "")).strip()

            if not discord_id.isdigit() or discord_id == "0":
                failed[username] = {**data, "reason": "無 Discord ID"}
                continue

            if discord_id in existing_ids:
                failed[username] = {**data, "reason": "Discord ID 已存在"}
                continue

            # 頻寬非 3MB/s 的需手動處理
            if data.get("speed_limit") not in LEGACY_3MB_VALUES:
                manual[username] = data
                continue

            # 隧道數與頻寬皆使用身分組的限制
            user = User(discord_id=discord_id, status=AccountStatus.SUSPENDED)
            user.roles.append(user_role)
            session.add(user)
            existing_ids.add(discord_id)
            imported += 1
            print(f"[新增] {username} ({discord_id})")

        await session.commit()

        print("\n匯入完成！")
        print(f"新增: {imported}")
        print(f"需手動處理: {len(manual)}")
        print(f"未寫入: {len(failed)}")

        return failed, manual


def dump_json(path: Path, data: dict[str, dict]):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    if not DATA_PATH.exists():
        print(f"找不到 {DATA_PATH}, 請確認檔案位置")
        sys.exit(1)

    with DATA_PATH.open(encoding="utf-8") as f:
        legacy_users = json.load(f)

    result = asyncio.run(import_users(legacy_users))
    if result is None:
        sys.exit(1)

    failed, manual = result

    if manual:
        dump_json(MANUAL_PATH, manual)
        print(f"需手動處理的使用者已輸出至 {MANUAL_PATH}")

    if failed:
        dump_json(FAILED_PATH, failed)
        print(f"未寫入的使用者已輸出至 {FAILED_PATH}")
