import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.models import Node, NodeStatus, TunnelProtocol
from app.routers.tunnels import TunnelCreateRequest, create_tunnel


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@dataclass
class _CurrentUser:
    internal_user_id: str


def _build_current_user() -> _CurrentUser:
    return _CurrentUser(internal_user_id="user-1")


def _build_active_node() -> Node:
    return Node(
        id=1,
        name="node-1",
        description=None,
        host="node.example.com",
        port_start=10000,
        port_end=20000,
        status=NodeStatus.ACTIVE,
        is_public=True,
        owner_id="owner-1",
    )


def _build_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/tunnels"})


def test_create_tunnel_requires_remote_port_for_tcp():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute.side_effect = [_Result(_build_active_node())]

    tunnel_data = TunnelCreateRequest(
        name="test-tunnel",
        description=None,
        node_id=1,
        protocol=TunnelProtocol.TCP,
        local_ip="127.0.0.1",
        local_port=8080,
        remote_port=None,
        is_kcp_enabled=True,
        is_proxy_protocol_v2_enabled=False,
    )

    with pytest.raises(HTTPException) as exec_info:
        asyncio.run(
            create_tunnel(
                request=_build_request(),
                response=MagicMock(),
                tunnel_data=tunnel_data,
                current_user=_build_current_user(),
                db=db,
            )
        )

    assert exec_info.value.status_code == 400
    assert exec_info.value.detail == "remote_port is required for TCP and UDP protocols"


def test_create_tunnel_integrity_error_message_is_clear():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.execute.side_effect = [_Result(_build_active_node()), _Result(None)]
    db.commit.side_effect = IntegrityError("stmt", "params", Exception("orig"))

    tunnel_data = TunnelCreateRequest(
        name="test-tunnel",
        description=None,
        node_id=1,
        protocol=TunnelProtocol.UDP,
        local_ip="127.0.0.1",
        local_port=8080,
        remote_port=12000,
        is_kcp_enabled=True,
        is_proxy_protocol_v2_enabled=False,
    )

    with pytest.raises(HTTPException) as exec_info:
        asyncio.run(
            create_tunnel(
                request=_build_request(),
                response=MagicMock(),
                tunnel_data=tunnel_data,
                current_user=_build_current_user(),
                db=db,
            )
        )

    assert exec_info.value.status_code == 409
    assert (
        exec_info.value.detail
        == "A tunnel with the same unique field already exists"
    )
