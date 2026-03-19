"""Tests for send_lxmf.sendmail (the sendmail-lxmf CLI)."""

import io
import importlib
import sys
import types
from unittest import mock

import pytest

VALID_HEX = "b9af7034186731b9f009d06795172a36"


# ---------------------------------------------------------------------------
# Email parsing (pure logic, no mocks needed)
# ---------------------------------------------------------------------------


class TestExtractLxmfAddress:
    """Unit tests for _extract_lxmf_address()."""

    def test_bare_hex(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(VALID_HEX) == VALID_HEX

    def test_angle_bracket(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(f"<{VALID_HEX}>") == VALID_HEX

    def test_name_angle_bracket(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(f"Alice <{VALID_HEX}>") == VALID_HEX

    def test_email_style(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(f"{VALID_HEX}@lxmf") == VALID_HEX

    def test_angle_bracket_email_style(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(f"Alice <{VALID_HEX}@lxmf>") == VALID_HEX

    def test_none_input(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(None) is None

    def test_empty_string(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address("") is None

    def test_invalid_string(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address("not-a-hash") is None

    def test_uppercase_normalised(self):
        from send_lxmf.sendmail import _extract_lxmf_address
        assert _extract_lxmf_address(VALID_HEX.upper()) == VALID_HEX


class TestParseEmail:
    """Unit tests for _parse_email()."""

    def test_plain_text_message(self):
        from send_lxmf.sendmail import _parse_email
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Hello\r\n"
            "\r\n"
            "Body text\r\n"
        )
        dest, raw_to, title, body, attachments, tmp_dir = _parse_email(raw)
        assert dest == VALID_HEX
        assert title == "Hello"
        assert "Body text" in body
        assert attachments == []
        assert tmp_dir is None

    def test_multipart_with_attachment(self, tmp_path):
        from send_lxmf.sendmail import _parse_email
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
        dest, raw_to, title, body, attachments, tmp_dir = _parse_email(raw)
        assert dest == VALID_HEX
        assert title == "With attachment"
        assert "See attached" in body
        assert len(attachments) == 1
        assert os.path.isfile(attachments[0])
        assert os.path.basename(attachments[0]) == "data.bin"
        assert tmp_dir is not None
        assert attachments[0].startswith(tmp_dir)
        with open(attachments[0], "rb") as f:
            assert f.read() == b"\x01\x02\x03\x04"
        # cleanup
        shutil.rmtree(tmp_dir)

    def test_no_to_header(self):
        from send_lxmf.sendmail import _parse_email
        raw = "Subject: No recipient\r\n\r\nBody\r\n"
        dest, raw_to, title, body, attachments, tmp_dir = _parse_email(raw)
        assert dest is None
        assert title == "No recipient"

    def test_no_subject(self):
        from send_lxmf.sendmail import _parse_email
        raw = f"To: {VALID_HEX}@lxmf\r\n\r\nBody\r\n"
        dest, raw_to, title, body, attachments, tmp_dir = _parse_email(raw)
        assert dest == VALID_HEX
        assert title == ""


# ---------------------------------------------------------------------------
# CLI integration tests (with mocked LXMF/RNS)
# ---------------------------------------------------------------------------


class TestSendmailCLI:
    """Integration tests for the sendmail-lxmf main() entry point."""

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
        assert "could not resolve" in capsys.readouterr().err.lower()

    def test_cli_recipient_overrides_to_header(self, monkeypatch):
        other_hex = "a" * 32
        raw = (
            f"To: {other_hex}@lxmf\r\n"
            "Subject: Test\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", VALID_HEX])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            spy.assert_called_once()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX]

    def test_subject_becomes_title(self, monkeypatch):
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Important\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            assert spy.call_args.kwargs["title"] == "Important"

    def test_recipient_from_to_header(self, monkeypatch):
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Hi\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX]

    def test_sendmail_compat_flags_accepted(self, monkeypatch):
        """Common sendmail flags like -i, -t, -f should not cause errors."""
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Hi\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", [
            "sendmail-lxmf", "-i", "-t", "-f", "sender@example.com",
        ])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send):
            _run_sendmail()  # should not raise

    def test_display_name_flag(self, monkeypatch):
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Hi\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", [
            "sendmail-lxmf", "--display-name", "Bob",
        ])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            assert spy.call_args.kwargs["display_name"] == "Bob"

    def test_F_flag_sets_display_name(self, monkeypatch):
        raw = (
            f"To: {VALID_HEX}@lxmf\r\n"
            "Subject: Hi\r\n"
            "\r\n"
            "Body\r\n"
        )
        monkeypatch.setattr(sys, "argv", [
            "sendmail-lxmf", "-F", "Carol",
        ])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            assert spy.call_args.kwargs["display_name"] == "Carol"


# ---------------------------------------------------------------------------
# Recipient resolution tests
# ---------------------------------------------------------------------------

ANOTHER_HEX = "a" * 32


class TestReadDefaultDestination:
    """Unit tests for _read_default_destination()."""

    def test_reads_bare_hash(self, tmp_path):
        from send_lxmf.sendmail import _read_default_destination
        f = tmp_path / "default-destination"
        f.write_text(f"{VALID_HEX}\n")
        assert _read_default_destination(str(f)) == VALID_HEX

    def test_skips_comments_and_blanks(self, tmp_path):
        from send_lxmf.sendmail import _read_default_destination
        f = tmp_path / "default-destination"
        f.write_text(f"# This is the admin\n\n{VALID_HEX}\n")
        assert _read_default_destination(str(f)) == VALID_HEX

    def test_returns_none_when_missing(self, tmp_path):
        from send_lxmf.sendmail import _read_default_destination
        assert _read_default_destination(str(tmp_path / "nope")) is None

    def test_returns_none_for_empty_file(self, tmp_path):
        from send_lxmf.sendmail import _read_default_destination
        f = tmp_path / "default-destination"
        f.write_text("")
        assert _read_default_destination(str(f)) is None


class TestReadAliases:
    """Unit tests for _read_aliases()."""

    def test_reads_aliases(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        f = tmp_path / "aliases"
        f.write_text(f"root: {VALID_HEX}\nadmin: {ANOTHER_HEX}\n")
        aliases = _read_aliases(str(f))
        assert aliases == {"root": [VALID_HEX], "admin": [ANOTHER_HEX]}

    def test_skips_comments_and_blanks(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        f = tmp_path / "aliases"
        f.write_text(f"# comment\n\nroot: {VALID_HEX}\n")
        aliases = _read_aliases(str(f))
        assert aliases == {"root": [VALID_HEX]}

    def test_case_insensitive_names(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        f = tmp_path / "aliases"
        f.write_text(f"Root: {VALID_HEX}\n")
        aliases = _read_aliases(str(f))
        assert "root" in aliases

    def test_returns_empty_when_missing(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        assert _read_aliases(str(tmp_path / "nope")) == {}

    def test_ignores_invalid_lines(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        f = tmp_path / "aliases"
        f.write_text(f"no-colon-here\nroot: {VALID_HEX}\nbad: not_a_hash\n")
        aliases = _read_aliases(str(f))
        assert aliases == {"root": [VALID_HEX]}

    def test_multiple_destinations(self, tmp_path):
        from send_lxmf.sendmail import _read_aliases
        f = tmp_path / "aliases"
        f.write_text(f"root: {VALID_HEX}, {ANOTHER_HEX}\n")
        aliases = _read_aliases(str(f))
        assert aliases == {"root": [VALID_HEX, ANOTHER_HEX]}


class TestResolveRecipient:
    """Unit tests for _resolve_recipient()."""

    def test_valid_lxmf_address_returned_directly(self, monkeypatch):
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient(VALID_HEX) == [VALID_HEX]

    def test_alias_lookup(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        f = tmp_path / "aliases"
        f.write_text(f"root: {VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(f))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("root") == [VALID_HEX]

    def test_alias_lookup_with_domain(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        f = tmp_path / "aliases"
        f.write_text(f"root: {VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(f))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("root@localhost") == [VALID_HEX]

    def test_falls_back_to_default_destination(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        f = tmp_path / "default-destination"
        f.write_text(f"{VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(tmp_path / "nope"))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(f))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("www-data") == [VALID_HEX]

    def test_returns_empty_when_nothing_configured(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(tmp_path / "nope"))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope2"))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("unknown") == []

    def test_alias_takes_precedence_over_default(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        aliases = tmp_path / "aliases"
        aliases.write_text(f"root: {ANOTHER_HEX}\n")
        default = tmp_path / "default-destination"
        default.write_text(f"{VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(aliases))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(default))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("root") == [ANOTHER_HEX]

    def test_multiple_destinations_from_alias(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        aliases = tmp_path / "aliases"
        aliases.write_text(f"root: {VALID_HEX}, {ANOTHER_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(aliases))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))
        from send_lxmf.sendmail import _resolve_recipient
        assert _resolve_recipient("root") == [VALID_HEX, ANOTHER_HEX]


class TestSendmailCLIRecipientResolution:
    """CLI integration tests for alias / default-destination resolution."""

    def test_local_user_resolved_via_alias(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        aliases = tmp_path / "aliases"
        aliases.write_text(f"root: {VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(aliases))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))

        raw = "To: root@localhost\r\nSubject: Alert\r\n\r\nDisk full\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            spy.assert_called_once()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX]

    def test_local_user_resolved_via_default(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        default = tmp_path / "default-destination"
        default.write_text(f"{VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(tmp_path / "nope"))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(default))

        raw = "To: nobody@localhost\r\nSubject: Alert\r\n\r\nSomething\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            spy.assert_called_once()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX]

    def test_cli_local_user_resolved_via_alias(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        aliases = tmp_path / "aliases"
        aliases.write_text(f"admin: {VALID_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(aliases))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))

        raw = "Subject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", "admin"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            spy.assert_called_once()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX]

    def test_unresolvable_recipient_exits_1(self, tmp_path, monkeypatch, capsys):
        import send_lxmf.sendmail as sm
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(tmp_path / "nope"))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope2"))

        raw = "Subject: Hi\r\n\r\nBody\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf", "unknown_user"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with pytest.raises(SystemExit) as exc:
            _run_sendmail()
        assert exc.value.code == 1
        assert "could not resolve" in capsys.readouterr().err.lower()

    def test_alias_with_multiple_destinations(self, tmp_path, monkeypatch):
        import send_lxmf.sendmail as sm
        aliases = tmp_path / "aliases"
        aliases.write_text(f"root: {VALID_HEX}, {ANOTHER_HEX}\n")
        monkeypatch.setattr(sm, "_ALIASES_PATH", str(aliases))
        monkeypatch.setattr(sm, "_DEFAULT_DEST_PATH", str(tmp_path / "nope"))

        raw = "To: root@localhost\r\nSubject: Alert\r\n\r\nDisk full\r\n"
        monkeypatch.setattr(sys, "argv", ["sendmail-lxmf"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        _simulate_delivery(monkeypatch)

        with mock.patch("send_lxmf.sendmail.send_message", wraps=_fake_send) as spy:
            _run_sendmail()
            spy.assert_called_once()
            assert spy.call_args.kwargs["destinations"] == [VALID_HEX, ANOTHER_HEX]


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


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
    import send_lxmf.lib as lib_mod
    import send_lxmf.sendmail as sendmail_mod
    importlib.reload(lib_mod)
    importlib.reload(sendmail_mod)
    yield


def _run_sendmail():
    from send_lxmf.sendmail import main
    main()


def _fake_send(**kwargs):
    """No-op replacement for send_message in CLI tests."""
    pass


def _simulate_delivery(monkeypatch):
    import LXMF

    def _handle(msg):
        cb = msg.register_delivery_callback.call_args[0][0]
        cb(msg)

    LXMF.LXMRouter.return_value.handle_outbound.side_effect = _handle
