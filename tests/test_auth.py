from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.redis_client import get_redis


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


def test_activate_account_requires_authentication(client: TestClient):
    response = client.get("/api/v1/auth/activate")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
