"""Tests for send_lxmf.pool.SenderPool."""

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

    link = mock.MagicMock()
    link.ACTIVE = 1
    link.CLOSED = 2
    link.status = 1
    rns.Link = link

    return rns


def _make_fake_lxmf():
    lxmf = types.ModuleType("LXMF")
    router_instance = mock.MagicMock()
    router_instance.register_delivery_identity.return_value = mock.MagicMock(
        hash=bytes.fromhex(VALID_HEX)
    )
    router_instance.outbound_propagation_link = mock.MagicMock()
    router_instance.outbound_propagation_link.status = 2
    lxmf.LXMRouter = mock.MagicMock(return_value=router_instance)

    msg = mock.MagicMock()
    msg.FAILED = 0
    msg.REJECTED = 1
    msg.CANCELLED = 2
    msg.state = 0
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
    import send_lxmf.pool as pool_mod
    importlib.reload(pool_mod)
    yield
    pool_mod.SenderPool._instance = None


def test_sender_pool_singleton():
    """SenderPool.get() returns the same instance on repeated calls."""
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    identity = mock.MagicMock()
    pool1 = SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")
    pool2 = SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

    assert pool1 is pool2


def test_sender_pool_creates_router_once():
    """The router is created only on the first send, reused thereafter."""
    import LXMF
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    identity = mock.MagicMock()
    pool = SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

    router = pool._get_router()
    router2 = pool._get_router()

    assert router is router2
    assert LXMF.LXMRouter.call_count == 1


def test_sender_pool_file_lock_instantiated():
    """File lock is instantiated with correct path and timeout."""
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    identity = mock.MagicMock()
    storage_path = "/tmp/storage"
    lock_path = "/tmp/locks/test.lock"

    pool = SenderPool.get(identity, storage_path, lock_path)

    assert pool._file_lock.lock_file == lock_path
    assert pool._file_lock.timeout == 30


def test_sender_pool_lock_context_manager(monkeypatch):
    """Lock is acquired/released via context manager during send."""
    import filelock
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    enter_count = [0]
    exit_count = [0]

    class MockFileLock:
        def __init__(self, path, timeout=None):
            self.lock_file = path
            self.timeout = timeout

        def __enter__(self):
            enter_count[0] += 1
            return self

        def __exit__(self, *args):
            exit_count[0] += 1
            return False

    monkeypatch.setattr(filelock, "FileLock", MockFileLock)

    import importlib
    import send_lxmf.pool as pool_mod
    importlib.reload(pool_mod)

    identity = mock.MagicMock()
    pool = pool_mod.SenderPool(identity, "/tmp/storage", "/tmp/locks/test.lock")

    dest_hash = bytes.fromhex(VALID_HEX)
    source_mock = mock.MagicMock()
    source_mock.hash = dest_hash

    import RNS

    RNS.Identity.recall.return_value = mock.MagicMock()

    import LXMF

    router_instance = pool._get_router()

    def simulate_delivery(msg):
        cb = msg.register_delivery_callback.call_args[0][0]
        cb(msg)

    router_instance.handle_outbound.side_effect = simulate_delivery

    try:
        pool.send(
            destination={
                "hash": dest_hash,
                "source": source_mock,
                "title": "",
                "fields": {},
                "timeout": 10,
                "propagation_node": None,
                "pn_hash": None,
            },
            content="test",
        )
    except Exception:
        pass

    assert enter_count[0] == 1
    assert exit_count[0] == 1


def test_pool_respects_system_lock_path(monkeypatch):
    """Pool uses the system lock path when provided."""
    import os
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    monkeypatch.setattr(os, "makedirs", mock.MagicMock())

    identity = mock.MagicMock()

    pool = SenderPool.get(
        identity,
        "/var/lib/send-lxmf/storage",
        "/var/run/send-lxmf/locks/send-lxmf.lock",
    )

    assert pool.storage_path == "/var/lib/send-lxmf/storage"
    assert pool._file_lock.lock_file == "/var/run/send-lxmf/locks/send-lxmf.lock"


def test_lock_dir_created_on_init(monkeypatch):
    """Lock directory is created with correct permissions on pool init."""
    import os
    from send_lxmf.pool import SenderPool

    SenderPool._instance = None

    makedirs_mock = mock.MagicMock()
    monkeypatch.setattr(os, "makedirs", makedirs_mock)

    import importlib
    import send_lxmf.pool as pool_mod
    importlib.reload(pool_mod)

    identity = mock.MagicMock()
    pool = pool_mod.SenderPool(identity, "/tmp/storage", "/var/run/send-lxmf/locks/test.lock")

    makedirs_mock.assert_called_once_with("/var/run/send-lxmf/locks", mode=0o755, exist_ok=True)