"""Tests for lxmf_sender.send (the send-lxmf CLI)."""

import io
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
    import lxmf_sender.send as send_mod

    importlib.reload(lib_mod)
    importlib.reload(send_mod)
    yield


class TestSendCLI:
    def test_no_args_prints_help(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["send-lxmf"])
        with pytest.raises(SystemExit) as exc:
            _run_main()
        assert exc.value.code == 0
        assert "usage" in capsys.readouterr().out.lower()

    def test_daemon_not_available_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
        from lxmf_sender.client import DaemonNotAvailableError

        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.side_effect = DaemonNotAvailableError("boom")
            with pytest.raises(SystemExit) as exc:
                _run_main()
            assert exc.value.code == 1
            assert "daemon not available" in capsys.readouterr().err.lower()

    def test_daemon_error_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("hello"))
        from lxmf_sender.client import DaemonResponseError

        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.side_effect = DaemonResponseError("bad thing")
            with pytest.raises(SystemExit) as exc:
                _run_main()
            assert exc.value.code == 1
            assert "bad thing" in capsys.readouterr().err.lower()

    def test_sends_message_via_daemon(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("hello world"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            instance.send_message.assert_called_once()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["destinations"] == [VALID_HEX]
            assert call_kwargs["content"] == "hello world"

    def test_title_flag_passed(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["send-lxmf", "--title", "My Title", VALID_HEX]
        )
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["title"] == "My Title"

    def test_attach_flag_passed(self, monkeypatch, tmp_path):
        f = tmp_path / "attachment.txt"
        f.write_text("data")
        monkeypatch.setattr(sys, "argv", ["send-lxmf", "--attach", str(f), VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            call_kwargs = instance.send_message.call_args.kwargs
            assert str(f) in call_kwargs["attachments"]

    def test_prepend_title_default_true(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["prepend_title"] is True

    def test_prepend_title_flag_false(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["send-lxmf", "--no-prepend-title", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["prepend_title"] is False

    def test_multiple_destinations(self, monkeypatch):
        hex2 = "a" * 32
        monkeypatch.setattr(sys, "argv", ["send-lxmf", VALID_HEX, hex2])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_main()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["destinations"] == [VALID_HEX, hex2]


def _run_main():
    from lxmf_sender.send import main

    main()
