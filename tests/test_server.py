"""Tests for lxmf_sender.server (the lxmf-sender daemon)."""

import asyncio
import os
import socket
import sys
import types
from unittest import mock

import pytest


VALID_HEX = "b9af7034186731b9f009d06795172a36"


def _make_fake_rns():
    rns = types.ModuleType("RNS")
    rns.Reticulum = mock.MagicMock()
    rns.log = mock.MagicMock()
    rns.prettyhexrep = lambda h: h.hex() if isinstance(h, bytes) else str(h)
    identity = mock.MagicMock()
    identity.from_file = mock.MagicMock(return_value=mock.MagicMock())
    identity.return_value = mock.MagicMock()
    identity.recall = mock.MagicMock(return_value=mock.MagicMock())
    rns.Identity = identity
    transport = mock.MagicMock()
    transport.has_path = mock.MagicMock(return_value=True)
    transport.request_path = mock.MagicMock()
    rns.Transport = transport
    destination = mock.MagicMock()
    destination.OUT = 1
    destination.SINGLE = 2
    rns.Destination = destination
    return rns


def _make_fake_lxmf():
    lxmf = types.ModuleType("LXMF")
    router_instance = mock.MagicMock()
    router_instance.register_delivery_identity.return_value = mock.MagicMock(
        hash=bytes.fromhex(VALID_HEX)
    )
    lxmf.LXMRouter = mock.MagicMock(return_value=router_instance)
    msg = mock.MagicMock()
    lxmf.LXMessage = mock.MagicMock(return_value=msg)
    lxmf.LXMessage.DIRECT = 0
    lxmf.LXMessage.OPPORTUNISTIC = 1
    lxmf.LXMessage.PROPAGATED = 2
    lxmf.FIELD_RENDERER = 0x0F
    lxmf.RENDERER_MARKDOWN = 0x02
    lxmf.FIELD_FILE_ATTACHMENTS = 0x05
    return lxmf


@pytest.fixture(autouse=True)
def _patch_modules(monkeypatch):
    fake_rns = _make_fake_rns()
    fake_lxmf = _make_fake_lxmf()
    monkeypatch.setitem(sys.modules, "RNS", fake_rns)
    monkeypatch.setitem(sys.modules, "LXMF", fake_lxmf)
    import importlib
    import lxmf_sender.lib as lib_mod
    import lxmf_sender.queue as queue_mod
    import lxmf_sender.server as server_mod

    importlib.reload(lib_mod)
    importlib.reload(queue_mod)
    importlib.reload(server_mod)
    yield


@pytest.fixture
def temp_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def daemon_with_queue(temp_dir):
    from lxmf_sender.server import LXMDaemon
    from lxmf_sender.queue import MessageQueue
    import LXMF

    d = LXMDaemon(
        data_dir=str(temp_dir),
        socket_path=str(temp_dir / "sock"),
    )
    db_path = str(temp_dir / "queue.db")
    d._queue = MessageQueue(db_path)
    d._router = LXMF.LXMRouter.return_value
    d._source = mock.MagicMock()
    yield d
    d.stop()


class TestAsyncHandleSend:
    def test_rejects_empty_destinations(self, daemon_with_queue):
        request = {"action": "send", "destinations": [], "content": "hello"}
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "error"
        assert "no destinations" in response["error"]

    def test_rejects_empty_content(self, daemon_with_queue):
        request = {"action": "send", "destinations": [VALID_HEX], "content": ""}
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "error"
        assert "no content" in response["error"]

    def test_rejects_invalid_destination(self, daemon_with_queue):
        request = {"action": "send", "destinations": ["not_hex"], "content": "hello"}
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "error"
        assert "invalid destination" in response["error"]

    def test_rejects_invalid_propagation_node(self, daemon_with_queue):
        request = {
            "action": "send",
            "destinations": [VALID_HEX],
            "content": "hello",
            "propagation_node": "invalid",
        }
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "error"
        assert "invalid propagation node" in response["error"]

    def test_rejects_missing_attachment_file(self, daemon_with_queue, temp_dir):
        request = {
            "action": "send",
            "destinations": [VALID_HEX],
            "content": "hello",
            "attachments": ["/nonexistent/file.txt"],
        }
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "error"
        assert "attachment not found" in response["error"]

    def test_enqueue_succeeds(self, daemon_with_queue, temp_dir):
        request = {
            "action": "send",
            "destinations": [VALID_HEX],
            "content": "hello",
            "title": "test",
        }
        response = asyncio.run(daemon_with_queue._handle_send(request))
        assert response["status"] == "queued"
        assert "queue_id" in response

    def test_ping_returns_ok(self, daemon_with_queue):
        response = asyncio.run(daemon_with_queue._handle_request({"action": "ping"}))
        assert response["status"] == "ok"
        assert "version" in response

    def test_unknown_action_returns_error(self, daemon_with_queue):
        response = asyncio.run(daemon_with_queue._handle_request({"action": "unknown"}))
        assert response["status"] == "error"
        assert "unknown action" in response["error"]
