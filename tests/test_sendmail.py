"""Tests for lxmf_sender.sendmail (the sendmail-lxmf CLI)."""

import io
import importlib
import sys
import types
from unittest import mock

import pytest

VALID_HEX = "b9af7034186731b9f009d06795172a36"
ANOTHER_HEX = "a" * 32


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
    import lxmf_sender.lib as lib_mod
    import lxmf_sender.sendmail as sendmail_mod

    importlib.reload(lib_mod)
    importlib.reload(sendmail_mod)
    yield


class TestExtractLxmfAddress:
    def test_bare_hex(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(VALID_HEX) == VALID_HEX

    def test_angle_bracket(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(f"<{VALID_HEX}>") == VALID_HEX

    def test_name_angle_bracket(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(f"Alice <{VALID_HEX}>") == VALID_HEX

    def test_email_style(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(f"{VALID_HEX}@lxmf") == VALID_HEX

    def test_angle_bracket_email_style(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(f"Alice <{VALID_HEX}@lxmf>") == VALID_HEX

    def test_none_input(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(None) is None

    def test_empty_string(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address("") is None

    def test_invalid_string(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address("not-a-hash") is None

    def test_uppercase_normalised(self):
        from lxmf_sender.sendmail import _extract_lxmf_address

        assert _extract_lxmf_address(VALID_HEX.upper()) == VALID_HEX


class TestParseEmail:
    def test_plain_text_message(self):
        from lxmf_sender.sendmail import _parse_email

        raw = f"To: {VALID_HEX}@lxmf\r\nSubject: Hello\r\n\r\nBody text\r\n"
        result = _parse_email(raw)
        assert result.to == f"{VALID_HEX}@lxmf"
        assert result.subject == "Hello"
        assert "Body text" in result.body
        assert result.attachments == []
        assert result.tmp_dir is None

    def test_multipart_with_attachment(self, tmp_path):
        from lxmf_sender.sendmail import _parse_email
        import os
        import shutil

        raw = (
            "MIME-Version: 1.0\r\n"
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: With attachment\r\n"
            'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
            "\r\n"
            "--BOUNDARY\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "See attached.\r\n"
            "--BOUNDARY\r\n"
            "Content-Type: application/octet-stream\r\n"
            'Content-Disposition: attachment; filename="data.bin"\r\n'
            "Content-Transfer-Encoding: base64\r\n"
            "\r\n"
            "AQIDBA==\r\n"
            "--BOUNDARY--\r\n"
        )
        result = _parse_email(raw)
        assert result.to == f"{VALID_HEX}@lxmf"
        assert result.subject == "With attachment"
        assert "See attached" in result.body
        assert len(result.attachments) == 1
        assert os.path.isfile(result.attachments[0])
        assert os.path.basename(result.attachments[0]) == "data.bin"
        assert result.tmp_dir is not None
        assert result.attachments[0].startswith(result.tmp_dir)
        with open(result.attachments[0], "rb") as f:
            assert f.read() == b"\x01\x02\x03\x04"
        shutil.rmtree(result.tmp_dir)

    def test_no_to_header(self):
        from lxmf_sender.sendmail import _parse_email

        raw = "Subject: No recipient\r\n\r\nBody\r\n"
        result = _parse_email(raw)
        assert result.to == ""
        assert result.subject == "No recipient"

    def test_no_subject(self):
        from lxmf_sender.sendmail import _parse_email

        raw = f"To: {VALID_HEX}@lxmf\r\n\r\nBody\r\n"
        result = _parse_email(raw)
        assert result.to == f"{VALID_HEX}@lxmf"
        assert result.subject == ""


class TestSendmailCLI:
    def test_empty_stdin_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc:
            _run_sendmail()
        assert exc.value.code == 1
        assert "no message provided" in capsys.readouterr().err.lower()

    def test_no_recipient_exits_1(self, monkeypatch, capsys):
        raw = "Subject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with pytest.raises(SystemExit) as exc:
            _run_sendmail()
        assert exc.value.code == 1
        assert "no recipient" in capsys.readouterr().err.lower()

    def test_invalid_cli_recipient_exits_1(self, monkeypatch, capsys):
        raw = "Subject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", "not_hex"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with pytest.raises(SystemExit) as exc:
            _run_sendmail()
        assert exc.value.code == 1
        assert "no recipient" in capsys.readouterr().err.lower()

    def test_cli_recipient_overrides_to_header(self, monkeypatch):
        other_hex = "a" * 32
        raw = f"To: {other_hex}@lxmf\r\nSubject: Test\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_sendmail()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["destinations"] == [VALID_HEX]

    def test_subject_becomes_title(self, monkeypatch):
        raw = f"To: {VALID_HEX}@lxmf\r\nSubject: Important\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_sendmail()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["title"] == "Important"

    def test_recipient_from_to_header(self, monkeypatch):
        raw = f"To: {VALID_HEX}@lxmf\r\nSubject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_sendmail()
            call_kwargs = instance.send_message.call_args.kwargs
            assert call_kwargs["destinations"] == [VALID_HEX]

    def test_sendmail_compat_flags_accepted(self, monkeypatch):
        raw = f"To: {VALID_HEX}@lxmf\r\nSubject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "sendmail-lxmf",
                "-i",
                "-t",
                "-f",
                "sender@example.com",
            ],
        )
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.return_value = {"status": "queued", "queue_id": 1}
            _run_sendmail()

    def test_daemon_not_available_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        from lxmf_sender.client import DaemonNotAvailableError

        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.side_effect = DaemonNotAvailableError("boom")
            with pytest.raises(SystemExit) as exc:
                _run_sendmail()
            assert exc.value.code == 1
            assert "daemon not available" in capsys.readouterr().err.lower()

    def test_daemon_error_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO("body"))
        from lxmf_sender.client import DaemonResponseError

        with mock.patch("lxmf_sender.client.DaemonClient") as mock_cls:
            instance = mock_cls.return_value
            instance.send_message.side_effect = DaemonResponseError("bad thing")
            with pytest.raises(SystemExit) as exc:
                _run_sendmail()
            assert exc.value.code == 1
            assert "bad thing" in capsys.readouterr().err.lower()


def _run_sendmail():
    from lxmf_sender.sendmail import main

    main()
