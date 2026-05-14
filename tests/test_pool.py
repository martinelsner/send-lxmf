"""Tests for send_lxmf.pool module-level state."""

import os
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
def _patch_and_reload(monkeypatch):
    """Patch modules and reload pool before each test."""
    fake_rns = _make_fake_rns()
    fake_lxmf = _make_fake_lxmf()
    monkeypatch.setitem(sys.modules, "RNS", fake_rns)
    monkeypatch.setitem(sys.modules, "LXMF", fake_lxmf)

    # Reset module-level state
    import send_lxmf.pool as pool_mod
    pool_mod._reset_for_testing()

    yield

    # Cleanup
    pool_mod._reset_for_testing()


@pytest.fixture
def mock_filelock(monkeypatch):
    """Mock filelock.FileLock."""
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

    monkeypatch.setattr("send_lxmf.pool.filelock.FileLock", MockFileLock)
    return enter_count, exit_count


class TestModuleLevelGet:
    """Tests for module-level get() function."""

    def test_get_creates_router_once(self):
        """get() creates router only on first call."""
        import LXMF
        import send_lxmf.pool as pool_mod

        identity = mock.MagicMock()
        router, source = pool_mod.get(
            identity, "/tmp/storage", "/tmp/locks/test.lock"
        )
        router2, source2 = pool_mod.get(
            identity, "/tmp/storage", "/tmp/locks/test.lock"
        )

        assert router is router2
        assert LXMF.LXMRouter.call_count == 1

    def test_get_returns_router_and_source(self):
        """get() returns tuple of (router, source)."""
        import send_lxmf.pool as pool_mod

        identity = mock.MagicMock()
        router, source = pool_mod.get(
            identity, "/tmp/storage", "/tmp/locks/test.lock"
        )

        assert router is not None
        assert source is not None

    def test_get_creates_file_lock(self, mock_filelock):
        """get() creates file lock with correct path and timeout."""
        import send_lxmf.pool as pool_mod

        identity = mock.MagicMock()
        enter_count, exit_count = mock_filelock

        pool_mod.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        assert pool_mod._file_lock.lock_file == "/tmp/locks/test.lock"
        assert pool_mod._file_lock.timeout == 30

    def test_get_creates_lock_dir(self, mock_filelock, monkeypatch):
        """get() creates lock directory with correct permissions."""
        import os
        import send_lxmf.pool as pool_mod

        makedirs_mock = mock.MagicMock()
        monkeypatch.setattr(os, "makedirs", makedirs_mock)

        identity = mock.MagicMock()
        pool_mod.get(identity, "/tmp/storage", "/var/run/send-lxmf/locks/test.lock")

        makedirs_mock.assert_called_once_with(
            "/var/run/send-lxmf/locks", mode=0o755, exist_ok=True
        )


class TestModuleLevelSend:
    """Tests for module-level send() function."""

    def test_send_acquires_lock(self, mock_filelock):
        """send() acquires file lock for the duration of send."""
        import send_lxmf.pool as pool_mod
        import RNS
        import LXMF

        enter_count, exit_count = mock_filelock

        identity = mock.MagicMock()
        pool_mod.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        dest_hash = bytes.fromhex(VALID_HEX)
        source_mock = mock.MagicMock()
        source_mock.hash = dest_hash

        RNS.Identity.recall.return_value = mock.MagicMock()

        router_instance = pool_mod._router

        def simulate_delivery(msg):
            cb = msg.register_delivery_callback.call_args[0][0]
            cb(msg)

        router_instance.handle_outbound.side_effect = simulate_delivery

        pool_mod.send(
            destination={
                "hash": dest_hash,
                "source": source_mock,
                "title": "",
                "fields": {},
                "timeout": 10,
                "propagation_node": None,
            },
            content="test",
        )

        assert enter_count[0] == 1
        assert exit_count[0] == 1

    def test_send_tries_direct_first(self, monkeypatch):
        """send() attempts direct delivery before propagated."""
        import send_lxmf.pool as pool_mod
        import RNS
        import LXMF

        identity = mock.MagicMock()
        pool_mod.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        dest_hash = bytes.fromhex(VALID_HEX)
        source_mock = mock.MagicMock()
        source_mock.hash = dest_hash

        RNS.Identity.recall.return_value = mock.MagicMock()

        router_instance = pool_mod._router
        call_order = []

        router_instance.handle_outbound.side_effect = lambda msg: call_order.append(
            "handle_outbound"
        )
        router_instance.process_outbound.return_value = None

        try:
            pool_mod.send(
                destination={
                    "hash": dest_hash,
                    "source": source_mock,
                    "title": "",
                    "fields": {},
                    "timeout": 0.1,
                    "propagation_node": None,
                },
                content="test",
            )
        except Exception:
            pass

        # Should have called handle_outbound at least once (for direct)
        assert "handle_outbound" in call_order


class TestSenderPoolBackwardsCompat:
    """Tests for backwards-compatible SenderPool class."""

    def test_sender_pool_get_returns_sender_pool(self):
        """SenderPool.get() returns SenderPool class for compat."""
        import send_lxmf.pool as pool_mod
        from send_lxmf.pool import SenderPool

        identity = mock.MagicMock()
        result = SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        assert result is SenderPool

    def test_sender_pool_direct_construction(self, mock_filelock):
        """SenderPool() construction initializes module state."""
        import send_lxmf.pool as pool_mod
        from send_lxmf.pool import SenderPool

        identity = mock.MagicMock()
        pool = SenderPool(identity, "/tmp/storage", "/tmp/locks/test.lock")

        assert pool_mod._router is not None
        assert pool_mod._file_lock is not None

    def test_sender_pool__get_router(self):
        """SenderPool._get_router() returns module router."""
        import send_lxmf.pool as pool_mod
        from send_lxmf.pool import SenderPool

        identity = mock.MagicMock()
        SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        # After get(), _router is set, so SenderPool() returns existing instance
        pool = SenderPool()
        router = pool._get_router()

        assert router is pool_mod._router

    def test_sender_pool_get_source(self):
        """SenderPool.get_source() returns module source."""
        import send_lxmf.pool as pool_mod
        from send_lxmf.pool import SenderPool

        identity = mock.MagicMock()
        SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        pool = SenderPool()
        source = pool.get_source()

        assert source is pool_mod._source

    def test_sender_pool_send_delegates_to_module_send(self, mock_filelock):
        """SenderPool.send() calls module-level send()."""
        import send_lxmf.pool as pool_mod
        from send_lxmf.pool import SenderPool
        import RNS

        identity = mock.MagicMock()
        SenderPool.get(identity, "/tmp/storage", "/tmp/locks/test.lock")

        dest_hash = bytes.fromhex(VALID_HEX)
        source_mock = mock.MagicMock()
        source_mock.hash = dest_hash

        RNS.Identity.recall.return_value = mock.MagicMock()

        router_instance = pool_mod._router

        def simulate_delivery(msg):
            cb = msg.register_delivery_callback.call_args[0][0]
            cb(msg)

        router_instance.handle_outbound.side_effect = simulate_delivery

        pool = SenderPool()
        pool.send(
            destination={
                "hash": dest_hash,
                "source": source_mock,
                "title": "",
                "fields": {},
                "timeout": 10,
                "propagation_node": None,
            },
            content="test",
        )

        enter_count, exit_count = mock_filelock
        assert enter_count[0] == 1
        assert exit_count[0] == 1