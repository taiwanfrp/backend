import json

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, RequirePermissions, get_current_user
from app.limiter import limiter
from app.models import AccountStatus, Role, User
from app.redis_client import get_redis
from app.schemas.users import (
    BECOME_NODE_PROVIDER_DOC,
    GET_CURRENT_USER_DOC,
    USER_CREATE_DOC,
    USER_DELETE_DOC,
    USER_NOT_FOUND_DOC,
    USER_UPDATE_DOC,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)

NODE_PROVIDER_ROLE_NAME = "node_provider"
DEFAULT_ROLE_NAME = "user"

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


def require_role_assign(current_user: CurrentUser):
    """
    指定使用者身份組時需要額外的 role.assign 權限
    """
    if "role.assign" not in current_user.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. Missing permissions: ['role.assign']",
        )


async def load_roles(db: AsyncSession, role_ids: list[int]) -> list[Role]:
    """
    依照 ID 取得身份組, 若有任何一個不存在則拋出 400
    """
    if not role_ids:
        return []

    stmt = (
        select(Role)
        .where(Role.id.in_(role_ids))
        .options(selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    roles = list(result.scalars().all())

    if len(roles) != len(set(role_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some roles not found",
        )

    return roles


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


@router.get("/me", response_model=CurrentUser, responses=GET_CURRENT_USER_DOC)  # type: ignore[arg-type]
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def read_current_user(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    獲取當前用戶信息的路由, 需要驗證
    """
    return current_user


@router.get("", response_model=list[UserResponse])
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_users(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(RequirePermissions(["user.read.all"])),
    db: AsyncSession = Depends(get_db),
):
    """
    列出所有使用者, 需要 user.read.all 權限
    """
    stmt = (
        select(User).options(selectinload(User.roles)).order_by(User.created_at.asc())
    )
    result = await db.execute(stmt)

    return result.scalars().all()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses=USER_NOT_FOUND_DOC,  # type: ignore[arg-type]
)
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/hour")  # type: ignore[arg-type]
async def get_user(
    request: Request,
    response: Response,
    user_id: str = Path(
        ..., max_length=36, description="使用者 ID (UUID) 或 Discord ID"
    ),
    current_user: CurrentUser = Depends(RequirePermissions(["user.read.all"])),
    db: AsyncSession = Depends(get_db),
):
    """
    取得指定使用者的資訊, 需要 user.read.all 權限
    - user_id 可傳入使用者 ID (UUID) 或 Discord ID (純數字)
    - 取得當前登入使用者的資訊請使用 /me
    """
    condition = User.discord_id == user_id if user_id.isdigit() else User.id == user_id
    stmt = select(User).where(condition).options(selectinload(User.roles))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.post(
    "/{discord_id}/activate",
    dependencies=[Depends(RequirePermissions(["user.activate"]))],
)
@limiter.limit("180/minute")  # type: ignore[arg-type]
@limiter.limit("7200/day")  # type: ignore[arg-type]
async def activate_user(
    discord_id: str,
    request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    啟用帳號
    """
    stmt = select(User).where(User.discord_id == discord_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with Discord ID not found",
        )

    if user.status == AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User account is already active",
        )

    user.status = AccountStatus.ACTIVE
    await db.commit()

    session_tokens = await redis.smembers(f"auth:user_sessions:{user.id}")

    for raw_token in session_tokens:
        token = (
            raw_token.decode("utf-8")
            if isinstance(raw_token, bytes)
            else str(raw_token)
        )

        session_json = await redis.get(f"auth:session:{token}")
        if session_json:
            user_data = json.loads(session_json)
            user_data["internal_user_status"] = AccountStatus.ACTIVE.value

            ttl = await redis.ttl(f"auth:session:{token}")
            if ttl > 0:
                await redis.set(
                    f"auth:session:{token}",
                    json.dumps(user_data),
                    ex=ttl,
                )
        else:
            await redis.srem(f"auth:user_sessions:{user.id}", token)

    return {
        "message": f"User {discord_id} activated successfully",
        "status": AccountStatus.ACTIVE.value,
    }


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses=USER_CREATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def create_user(
    request: Request,
    response: Response,
    payload: UserCreateRequest,
    current_user: CurrentUser = Depends(RequirePermissions(["user.create"])),
    db: AsyncSession = Depends(get_db),
):
    """
    建立使用者帳號, 需要 user.create 權限
    - 未傳入 role_ids 時預設給予 user 身份組
    - 傳入 role_ids 時需要 role.assign 權限
    """
    stmt = select(User).where(User.discord_id == payload.discord_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with Discord ID already exists",
        )

    if payload.role_ids is None:
        role_stmt = select(Role).where(Role.name == DEFAULT_ROLE_NAME)
        default_role = (await db.execute(role_stmt)).scalar_one_or_none()
        roles = [default_role] if default_role else []
    else:
        require_role_assign(current_user)
        roles = await load_roles(db, payload.role_ids)

    new_user = User(
        discord_id=payload.discord_id,
        status=payload.status,
        custom_max_tunnels=payload.custom_max_tunnels,
        custom_max_bandwidth=payload.custom_max_bandwidth,
    )
    new_user.roles = roles

    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with Discord ID already exists",
        )

    return new_user


@router.patch(
    "/{discord_id}",
    response_model=UserResponse,
    responses=USER_UPDATE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def update_user(
    discord_id: str,
    request: Request,
    response: Response,
    payload: UserUpdateRequest,
    current_user: CurrentUser = Depends(RequirePermissions(["user.update.all"])),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    更新使用者帳號, 需要 user.update.all 權限
    - custom_max_tunnels / custom_max_bandwidth 傳入 null 表示改回使用身份組的限制
    - role_ids 會取代使用者現有的身份組, 需要 role.assign 權限
    - 不能修改自己的狀態與身份組
    - 更新後會同步到該使用者所有登入 session
    """
    stmt = (
        select(User)
        .where(User.discord_id == discord_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with Discord ID not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return user

    if user.id == current_user.internal_user_id and (
        "status" in update_data or "role_ids" in update_data
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own status or roles",
        )

    if "role_ids" in update_data:
        require_role_assign(current_user)
        user.roles = await load_roles(db, update_data["role_ids"])

    if "status" in update_data:
        user.status = update_data["status"]
    if "custom_max_tunnels" in update_data:
        user.custom_max_tunnels = update_data["custom_max_tunnels"]
    if "custom_max_bandwidth" in update_data:
        user.custom_max_bandwidth = update_data["custom_max_bandwidth"]

    await db.commit()
    await sync_user_sessions(redis, user)

    return user


@router.delete(
    "/{discord_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=USER_DELETE_DOC,  # type: ignore[arg-type]
)
@limiter.limit("60/hour")  # type: ignore[arg-type]
@limiter.limit("180/day")  # type: ignore[arg-type]
async def delete_user(
    discord_id: str,
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(RequirePermissions(["user.delete.all"])),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除使用者帳號, 需要 user.delete.all 權限
    - 硬刪除: 連同使用者的節點 (含節點上所有隧道), 隧道, API Key 一併刪除
    - 同時清除該使用者所有登入 session, 使其立即登出
    - 不能刪除自己的帳號
    """
    if discord_id == current_user.discord_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    stmt = select(User).where(User.discord_id == discord_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with Discord ID not found",
        )

    await db.delete(user)
    await db.commit()

    # 清除所有 session 與權限快取
    session_tokens = await redis.smembers(f"auth:user_sessions:{user.id}")
    for raw_token in session_tokens:
        token = (
            raw_token.decode("utf-8")
            if isinstance(raw_token, bytes)
            else str(raw_token)
        )
        await redis.delete(f"auth:session:{token}")

    await redis.delete(
        f"auth:user_sessions:{user.id}",
        f"auth:permissions:{user.id}",
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/become-node-provider",
    response_model=CurrentUser,
    responses=BECOME_NODE_PROVIDER_DOC,  # type: ignore[arg-type]
    dependencies=[Depends(RequirePermissions(["user.update.own"]))],
)
@limiter.limit("10/hour")  # type: ignore[arg-type]
@limiter.limit("30/day")  # type: ignore[arg-type]
async def become_node_provider(
    request: Request,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    使用者自助取得節點提供者資格 (node_provider 身分組), 使其獲得 node.create 權限
    """
    stmt = (
        select(User)
        .where(User.id == current_user.internal_user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if any(role.name == NODE_PROVIDER_ROLE_NAME for role in user.roles):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a node provider",
        )

    role_stmt = (
        select(Role)
        .where(Role.name == NODE_PROVIDER_ROLE_NAME)
        .options(selectinload(Role.permissions))
    )
    node_provider_role = (await db.execute(role_stmt)).scalar_one_or_none()

    if not node_provider_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="node_provider role is not seeded",
        )

    user.roles.append(node_provider_role)
    await db.commit()
    await db.refresh(user)

    user_permissions = list(
        {permission.name for role in user.roles for permission in role.permissions}
    )

    roles_list = [role.name for role in user.roles]

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
            session_data["roles"] = roles_list

            ttl = await redis.ttl(f"auth:session:{token}")
            if ttl > 0:
                await redis.set(
                    f"auth:session:{token}",
                    json.dumps(session_data),
                    ex=ttl,
                )
        else:
            await redis.srem(f"auth:user_sessions:{user.id}", token)

    return current_user.model_copy(
        update={"roles": roles_list, "permissions": user_permissions}
    )
