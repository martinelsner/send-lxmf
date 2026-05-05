"""Tests for send_lxmf.send.main() (the send-lxmf CLI)."""

import io
import sys
import types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_args_prints_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["send-lxmf"])
    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_invalid_hex_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["send-lxmf", "not_hex"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "not a valid hex" in capsys.readouterr().err


def test_empty_stdin_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "no message content" in capsys.readouterr().err.lower()


def test_missing_identity_file_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "send-lxmf", VALID_HEX,
        "--identity", "/nonexistent/path/id",
    ])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "identity file not found" in capsys.readouterr().err.lower()


def test_loads_identity_from_explicit_path(monkeypatch, tmp_path):
    import RNS
    id_file = tmp_path / "my_id"
    id_file.write_text("fake")
    monkeypatch.setattr(sys, "argv", [
        "send-lxmf", VALID_HEX,
        "--identity", str(id_file),
    ])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    _simulate_delivery(monkeypatch)

    _run_main()
    RNS.Identity.from_file.assert_called_once_with(str(id_file))


def test_loads_identity_from_system_path(monkeypatch, tmp_path):
    import RNS
    id_file = tmp_path / "identity"
    id_file.write_text("fake")
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    monkeypatch.setattr("send_lxmf.lib.SYSTEM_IDENTITY_PATH", str(id_file))
    _simulate_delivery(monkeypatch)

    _run_main()
    RNS.Identity.from_file.assert_called_with(str(id_file))


def test_auto_creates_system_identity(monkeypatch, tmp_path):
    import RNS
    id_file = tmp_path / "identity"
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    monkeypatch.setattr("send_lxmf.lib.SYSTEM_IDENTITY_PATH", str(id_file))
    _simulate_delivery(monkeypatch)

    original_to_file = RNS.Identity.return_value.to_file
    _run_main()
    original_to_file.assert_called_with(str(id_file))


def test_failed_delivery_exits_1(monkeypatch, capsys):
    import LXMF
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))

    def _handle(msg):
        cb = msg.register_failed_callback.call_args[0][0]
        cb(msg)

    LXMF.LXMRouter.return_value.handle_outbound.side_effect = _handle

    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "delivery failed" in capsys.readouterr().err.lower()


def test_path_timeout_exits_1(monkeypatch, capsys):
    """With TIMEOUT=0 and no path, opportunistic delivery times out."""
    import RNS
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    monkeypatch.setattr("send_lxmf.lib.TIMEOUT", 0)
    RNS.Transport.has_path.return_value = False
    RNS.Identity.recall.return_value = None

    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1


def test_identity_timeout_exits_1(monkeypatch, capsys):
    import RNS
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    monkeypatch.setattr("send_lxmf.lib.TIMEOUT", 0)
    RNS.Transport.has_path.return_value = True
    RNS.Identity.recall.return_value = None

    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "timed out waiting for recipient identity" in capsys.readouterr().err.lower()


def test_delivery_timeout_exits_1(monkeypatch, capsys):
    """With TIMEOUT=0 and no callback fired, delivery times out."""
    import LXMF
    monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
    monkeypatch.setattr("send_lxmf.lib.TIMEOUT", 0)
    LXMF.LXMRouter.return_value.handle_outbound.side_effect = None

    with pytest.raises(SystemExit) as exc:
        _run_main()
    assert exc.value.code == 1
    assert "delivery failed" in capsys.readouterr().err.lower()


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

VALID_HEX = "b9af7034186731b9f009d06795172a36"


def _make_fake_rns():
    """Return a fake RNS module with the minimal surface used by send_message()."""
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
    """Inject fake RNS / LXMF into sys.modules before every test."""
    import os

    monkeypatch.setattr(os, "makedirs", mock.MagicMock())
    fake_rns = _make_fake_rns()
    fake_lxmf = _make_fake_lxmf()
    monkeypatch.setitem(sys.modules, "RNS", fake_rns)
    monkeypatch.setitem(sys.modules, "LXMF", fake_lxmf)

    import types

    fake_filelock = types.ModuleType("filelock")

    class MockFileLock:
        def __init__(self, path, timeout=None):
            self.lock_file = path
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    fake_filelock.FileLock = MockFileLock
    monkeypatch.setitem(sys.modules, "filelock", fake_filelock)

    import importlib
    import send_lxmf.lib as lib_mod
    import send_lxmf.pool as pool_mod
    import send_lxmf.send as send_mod
    pool_mod.SenderPool._instance = None
    importlib.reload(lib_mod)
    importlib.reload(pool_mod)
    importlib.reload(send_mod)
    yield
    pool_mod.SenderPool._instance = None


def _run_main():
    from send_lxmf.send import main
    main()


def _simulate_delivery(monkeypatch):
    """Patch handle_outbound to immediately fire the delivery callback."""
    import LXMF

    def _handle(msg):
        cb = msg.register_delivery_callback.call_args[0][0]
        cb(msg)

    LXMF.LXMRouter.return_value.handle_outbound.side_effect = _handle
