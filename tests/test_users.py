import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user
from app.main import app
from app.models import AccountStatus, Permission, Role, User
from app.redis_client import get_redis
from app.routers.users import get_me_user

ADMIN_DISCORD_ID = "100000000000000001"
TARGET_DISCORD_ID = "100000000000000002"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeRedis:
    def __init__(self, sessions: dict[str, set[str]] | None = None):
        self.store: dict[str, object] = {}
        for user_id, tokens in (sessions or {}).items():
            self.store[f"auth:user_sessions:{user_id}"] = set(tokens)
            self.store[f"auth:permissions:{user_id}"] = "[]"
            for token in tokens:
                self.store[f"auth:session:{token}"] = "{}"

    async def smembers(self, key: str):
        value = self.store.get(key, set())
        return set(value) if isinstance(value, set) else set()

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value
        return True

    async def ttl(self, key: str):
        return 3600 if key in self.store else -2

    async def srem(self, key: str, *values: str):
        members = self.store.get(key)
        if isinstance(members, set):
            members.difference_update(values)
        return len(values)

    async def delete(self, *keys: str):
        return sum(1 for key in keys if self.store.pop(key, None) is not None)


class FakeScalars:
    def __init__(self, value):
        self.value = value

    def all(self):
        return self.value


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return FakeScalars(self.value)


class FakeDB:
    """
    依序回傳 results 中的查詢結果
    """

    def __init__(self, results: list):
        self.results = list(results)
        self.statements: list[str] = []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.committed = False

    async def execute(self, stmt):
        self.statements.append(str(stmt))
        return FakeResult(self.results.pop(0))

    def add(self, instance):
        self.added.append(instance)

    async def delete(self, instance):
        self.deleted.append(instance)

    async def commit(self):
        # 模擬資料庫寫入時產生的欄位
        for instance in self.added:
            for field in ("created_at", "updated_at"):
                if getattr(instance, field, None) is None:
                    setattr(instance, field, NOW)
            if isinstance(instance, User) and instance.id is None:
                instance.id = "new-user-id"
        self.committed = True

    async def rollback(self):
        return None


def make_current_user(permissions: list[str]) -> CurrentUser:
    return CurrentUser(
        internal_user_id="admin-id",
        internal_account_status="active",
        discord_id=ADMIN_DISCORD_ID,
        username="admin",
        avatar=None,
        mfa_enabled=False,
        locale="en-US",
        email=None,
        verified=True,
        permissions=permissions,
    )


def make_role(role_id: int, name: str, max_tunnels: int = 3) -> Role:
    return Role(
        id=role_id,
        name=name,
        max_tunnels=max_tunnels,
        max_bandwidth=3,
        permissions=[Permission(name=f"{name}.perm")],
    )


def make_user(user_id: str = "target-id", discord_id: str = TARGET_DISCORD_ID) -> User:
    return User(
        id=user_id,
        discord_id=discord_id,
        status=AccountStatus.SUSPENDED,
        roles=[make_role(1, "user")],
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture()
def setup_client():
    def _setup(
        results: list,
        permissions: list[str],
        redis: FakeRedis | None = None,
    ) -> tuple[TestClient, FakeDB, FakeRedis]:
        db = FakeDB(results)
        fake_redis = redis or FakeRedis()
        current_user = make_current_user(permissions)

        async def override_get_db():
            yield db

        async def override_get_redis():
            yield fake_redis

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_redis] = override_get_redis
        app.dependency_overrides[get_current_user] = lambda: current_user
        app.dependency_overrides[get_me_user] = lambda: current_user
        return TestClient(app), db, fake_redis

    yield _setup
    app.dependency_overrides.clear()


# 查詢使用者


def test_get_users(setup_client):
    users = [make_user(), make_user(user_id="other-id", discord_id="1" * 18)]
    client, _, _ = setup_client([users], ["user.read.all"])

    response = client.get("/api/v1/users")

    assert response.status_code == 200
    body = response.json()
    assert [user["id"] for user in body] == ["target-id", "other-id"]
    assert body[0] == {
        "id": "target-id",
        "discord_id": TARGET_DISCORD_ID,
        "status": "suspended",
        "custom_max_tunnels": None,
        "custom_max_bandwidth": None,
        "roles": [{"id": 1, "name": "user"}],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


def test_get_users_requires_permission(setup_client):
    client, _, _ = setup_client([], ["user.read.own"])

    response = client.get("/api/v1/users")

    assert response.status_code == 403


def test_get_user_by_discord_id(setup_client):
    client, db, _ = setup_client([make_user()], ["user.read.all"])

    response = client.get(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == "target-id"
    assert "users.discord_id =" in db.statements[0]


def test_get_user_by_uuid(setup_client):
    user_uuid = "01a14d41-045a-7c19-899b-c6d550dcaa8f"
    client, db, _ = setup_client([make_user(user_id=user_uuid)], ["user.read.all"])

    response = client.get(f"/api/v1/users/{user_uuid}")

    assert response.status_code == 200
    assert response.json()["id"] == user_uuid
    assert "users.id =" in db.statements[0]


def test_get_user_not_found(setup_client):
    client, _, _ = setup_client([None], ["user.read.all"])

    response = client.get(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_get_user_requires_permission(setup_client):
    client, _, _ = setup_client([], ["user.read.own"])

    response = client.get(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 403


def test_get_me_is_not_treated_as_user_id(setup_client):
    client, db, _ = setup_client([], [])

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["discord_id"] == ADMIN_DISCORD_ID
    assert db.statements == []


# 建立使用者


def test_create_user_with_default_role(setup_client):
    default_role = make_role(1, "user")
    client, db, _ = setup_client([None, default_role], ["user.create"])

    response = client.post(
        "/api/v1/users",
        json={"discord_id": TARGET_DISCORD_ID, "custom_max_tunnels": 5},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["discord_id"] == TARGET_DISCORD_ID
    assert body["status"] == "suspended"
    assert body["custom_max_tunnels"] == 5
    assert body["custom_max_bandwidth"] is None
    assert body["roles"] == [{"id": 1, "name": "user"}]
    assert db.committed


def test_create_user_already_exists(setup_client):
    client, db, _ = setup_client([make_user()], ["user.create"])

    response = client.post("/api/v1/users", json={"discord_id": TARGET_DISCORD_ID})

    assert response.status_code == 409
    assert not db.committed


def test_create_user_with_roles_requires_role_assign(setup_client):
    client, db, _ = setup_client([None], ["user.create"])

    response = client.post(
        "/api/v1/users", json={"discord_id": TARGET_DISCORD_ID, "role_ids": [2]}
    )

    assert response.status_code == 403
    assert not db.committed


def test_create_user_with_unknown_role(setup_client):
    client, db, _ = setup_client([None, []], ["user.create", "role.assign"])

    response = client.post(
        "/api/v1/users", json={"discord_id": TARGET_DISCORD_ID, "role_ids": [99]}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Some roles not found"}
    assert not db.committed


def test_create_user_invalid_discord_id(setup_client):
    client, _, _ = setup_client([], ["user.create"])

    response = client.post("/api/v1/users", json={"discord_id": "not-a-number"})

    assert response.status_code == 422


def test_create_user_requires_permission(setup_client):
    client, db, _ = setup_client([], ["user.read.own"])

    response = client.post("/api/v1/users", json={"discord_id": TARGET_DISCORD_ID})

    assert response.status_code == 403
    assert not db.committed


# 更新使用者


def test_update_user_and_sync_sessions(setup_client):
    user = make_user()
    redis = FakeRedis(sessions={"target-id": {"token-a"}})
    redis.store["auth:session:token-a"] = json.dumps(
        {"internal_account_status": "suspended", "roles": ["user"]}
    )
    new_roles = [make_role(1, "user"), make_role(2, "vip", max_tunnels=10)]
    client, db, redis = setup_client(
        [user, new_roles], ["user.update.all", "role.assign"], redis=redis
    )

    response = client.patch(
        f"/api/v1/users/{TARGET_DISCORD_ID}",
        json={
            "status": "active",
            "custom_max_bandwidth": 50,
            "role_ids": [1, 2],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["custom_max_bandwidth"] == 50
    assert [role["name"] for role in body["roles"]] == ["user", "vip"]
    assert db.committed

    session = json.loads(redis.store["auth:session:token-a"])
    assert session["internal_account_status"] == "active"
    assert session["roles"] == ["user", "vip"]
    assert session["limits"] == {"max_tunnels": 10, "max_bandwidth": 50}
    assert set(json.loads(redis.store["auth:permissions:target-id"])) == {
        "user.perm",
        "vip.perm",
    }


def test_update_user_null_custom_limit_resets_to_role(setup_client):
    user = make_user()
    user.custom_max_tunnels = 5
    client, _, _ = setup_client([user], ["user.update.all"])

    response = client.patch(
        f"/api/v1/users/{TARGET_DISCORD_ID}", json={"custom_max_tunnels": None}
    )

    assert response.status_code == 200
    assert response.json()["custom_max_tunnels"] is None


def test_update_user_rejects_null_status(setup_client):
    client, _, _ = setup_client([], ["user.update.all"])

    response = client.patch(f"/api/v1/users/{TARGET_DISCORD_ID}", json={"status": None})

    assert response.status_code == 422


def test_update_user_cannot_change_own_status(setup_client):
    me = make_user(user_id="admin-id", discord_id=ADMIN_DISCORD_ID)
    client, db, _ = setup_client([me], ["user.update.all"])

    response = client.patch(
        f"/api/v1/users/{ADMIN_DISCORD_ID}", json={"status": "suspended"}
    )

    assert response.status_code == 400
    assert not db.committed


def test_update_user_roles_requires_role_assign(setup_client):
    client, db, _ = setup_client([make_user()], ["user.update.all"])

    response = client.patch(
        f"/api/v1/users/{TARGET_DISCORD_ID}", json={"role_ids": [1]}
    )

    assert response.status_code == 403
    assert not db.committed


def test_update_user_not_found(setup_client):
    client, _, _ = setup_client([None], ["user.update.all"])

    response = client.patch(
        f"/api/v1/users/{TARGET_DISCORD_ID}", json={"status": "active"}
    )

    assert response.status_code == 404


# 啟用帳號


def test_activate_user_updates_sessions(setup_client):
    user = make_user()
    redis = FakeRedis(sessions={"target-id": {"token-a"}})
    redis.store["auth:session:token-a"] = json.dumps(
        {"internal_account_status": "suspended"}
    )
    client, db, redis = setup_client([user], ["user.activate"], redis=redis)

    response = client.post(f"/api/v1/users/{TARGET_DISCORD_ID}/activate")

    assert response.status_code == 200
    assert user.status == AccountStatus.ACTIVE
    assert db.committed
    # 已經登入的 session 也要更新, 不用重新登入
    session = json.loads(redis.store["auth:session:token-a"])
    assert session["internal_account_status"] == "active"


# 刪除使用者


def test_delete_user_hard_deletes_and_clears_sessions(setup_client):
    user = make_user()
    redis = FakeRedis(sessions={"target-id": {"token-a", "token-b"}})
    client, db, redis = setup_client([user], ["user.delete.all"], redis=redis)

    response = client.delete(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 204
    assert db.deleted == [user]
    assert db.committed
    assert redis.store == {}


def test_delete_user_cannot_delete_self(setup_client):
    client, db, _ = setup_client([make_user()], ["user.delete.all"])

    response = client.delete(f"/api/v1/users/{ADMIN_DISCORD_ID}")

    assert response.status_code == 400
    assert response.json() == {"detail": "Cannot delete your own account"}
    assert db.deleted == []


def test_delete_user_not_found(setup_client):
    client, _, _ = setup_client([None], ["user.delete.all"])

    response = client.delete(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 404


def test_delete_user_requires_permission(setup_client):
    client, db, _ = setup_client([make_user()], ["user.read.own"])

    response = client.delete(f"/api/v1/users/{TARGET_DISCORD_ID}")

    assert response.status_code == 403
    assert db.deleted == []
