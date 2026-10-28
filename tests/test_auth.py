import json
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.redis_client import get_redis
from app.utils.tokens import hash_session_token


class DummyRedis:
    async def get(self, key: str):
        return None

    async def expire(self, key: str, ttl: int):
        return True

    async def set(self, key: str, value: str, ex: int | None = None):
        return True

    async def delete(self, key: str):
        return 1


class DummyDB:
    async def execute(self, stmt):
        raise AssertionError("DB should not be queried when no current user exists")

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def override_get_redis() -> DummyRedis:
    return DummyRedis()


async def override_get_db() -> AsyncGenerator[DummyDB, None]:
    session = DummyDB()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# def test_activate_account_requires_authentication(client: TestClient):
#     response = client.get("/api/v1/auth/activate")

#     assert response.status_code == 401
#     assert response.json() == {"detail": "Not authenticated"}


SESSION_TOKEN = "session-token"
ORIGIN = settings.cors_origins.split(",")[0]


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def expire(self, key: str, ttl: int):
        self.ttls[key] = ttl
        return key in self.store

    async def set(self, key: str, value: str, ex: int | None = None):
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, key: str):
        return 1 if self.store.pop(key, None) is not None else 0


def make_session(status: str = "active") -> str:
    return json.dumps(
        {
            "internal_user_id": "user-id",
            "internal_account_status": status,
            "discord_id": "100000000000000001",
            "username": "user",
            "avatar": None,
            "mfa_enabled": False,
            "locale": "zh-TW",
            "email": None,
            "verified": True,
            "roles": ["user"],
            "limits": {"max_tunnels": 3, "max_bandwidth": 3},
        }
    )


@pytest.fixture()
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture()
def session_client(fake_redis: FakeRedis) -> Generator[TestClient, None, None]:
    async def override_fake_redis() -> FakeRedis:
        return fake_redis

    app.dependency_overrides[get_redis] = override_fake_redis
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, redis: FakeRedis, status: str = "active"):
    """
    模擬登入: Redis 的 key 是 session token 的雜湊
    """
    redis.store[f"auth:session:{hash_session_token(SESSION_TOKEN)}"] = make_session(
        status
    )
    client.cookies.set(settings.cookie_auth_name, SESSION_TOKEN)


def test_session_is_stored_by_hash(session_client: TestClient, fake_redis: FakeRedis):
    fake_redis.store[f"auth:session:{SESSION_TOKEN}"] = make_session()
    session_client.cookies.set(settings.cookie_auth_name, SESSION_TOKEN)
    # 用原始 token 當 key 的 session 不能使用
    assert session_client.get("/api/v1/users/me").status_code == 401

    login(session_client, fake_redis)
    response = session_client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["discord_id"] == "100000000000000001"


def test_me_allows_suspended_account(session_client: TestClient, fake_redis: FakeRedis):
    login(session_client, fake_redis, status="suspended")
    response = session_client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["internal_account_status"] == "suspended"

    # 其他 API 仍然只接受啟用中的帳號
    response = session_client.get("/api/v1/permissions")
    assert response.status_code == 403
    assert response.json() == {"detail": "Account is suspended"}


@pytest.mark.parametrize("status", ["banned", "deleted"])
def test_me_rejects_unusable_account(
    session_client: TestClient, fake_redis: FakeRedis, status: str
):
    login(session_client, fake_redis, status=status)
    response = session_client.get("/api/v1/users/me")

    assert response.status_code == 403
    assert response.json() == {"detail": f"Account is {status}"}


def test_logout_deletes_hashed_session(
    session_client: TestClient, fake_redis: FakeRedis
):
    login(session_client, fake_redis)
    response = session_client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert f"auth:session:{hash_session_token(SESSION_TOKEN)}" not in fake_redis.store


def test_create_ticket_code(session_client: TestClient, fake_redis: FakeRedis):
    login(session_client, fake_redis)
    response = session_client.post(
        "/api/v1/auth/ticket-code", headers={"Origin": ORIGIN}
    )

    assert response.status_code == 200
    code = response.json()["code"]
    key = f"auth:ticket_code:{code}"
    # 授權碼只對應到 session 的雜湊, 30 秒後過期
    assert fake_redis.store[key] == hash_session_token(SESSION_TOKEN)
    assert fake_redis.ttls[key] == 30


def test_create_ticket_code_allows_suspended_account(
    session_client: TestClient, fake_redis: FakeRedis
):
    login(session_client, fake_redis, status="suspended")
    response = session_client.post(
        "/api/v1/auth/ticket-code", headers={"Origin": ORIGIN}
    )

    assert response.status_code == 200


@pytest.mark.parametrize("status", ["banned", "deleted"])
def test_create_ticket_code_rejects_unusable_account(
    session_client: TestClient, fake_redis: FakeRedis, status: str
):
    login(session_client, fake_redis, status=status)
    response = session_client.post(
        "/api/v1/auth/ticket-code", headers={"Origin": ORIGIN}
    )

    assert response.status_code == 401
    assert not any(key.startswith("auth:ticket_code:") for key in fake_redis.store)


def test_create_ticket_code_requires_session(session_client: TestClient):
    response = session_client.post(
        "/api/v1/auth/ticket-code", headers={"Origin": ORIGIN}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_create_ticket_code_rejects_other_origin(
    session_client: TestClient, fake_redis: FakeRedis
):
    login(session_client, fake_redis)
    response = session_client.post(
        "/api/v1/auth/ticket-code", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Origin not allowed"}
    assert not any(key.startswith("auth:ticket_code:") for key in fake_redis.store)
