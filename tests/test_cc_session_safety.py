from __future__ import annotations

from xiaozhi_desktop_mcp.tools import cc_session


def test_send_instruction_requires_registered_session(settings, monkeypatch):
    called = False

    def fake_send(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cc_session, "_send_to_visible_terminal", fake_send)

    result = cc_session.send_instruction(settings, "hello", "missing")

    assert result["success"] is False
    assert "not registered" in result["error"]
    assert called is False


def test_send_decision_requires_registered_session(settings, monkeypatch):
    called = False

    def fake_send(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cc_session, "_send_to_visible_terminal", fake_send)

    result = cc_session.send_decision(settings, "yes", "missing", confirm=True)

    assert result["success"] is False
    assert "not registered" in result["error"]
    assert called is False


def test_stop_session_requires_registered_session(settings, monkeypatch):
    called = False

    def fake_send(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cc_session, "_send_to_visible_terminal", fake_send)

    result = cc_session.stop_session("missing")

    assert result["success"] is False
    assert "not registered" in result["error"]
    assert called is False


def test_allow_frontmost_is_explicit_for_instruction(settings, monkeypatch):
    sent = []

    def fake_send(terminal, text):
        sent.append((terminal, text))

    monkeypatch.setattr(cc_session, "_send_to_visible_terminal", fake_send)

    result = cc_session.send_instruction(settings, "hello", "missing", allow_frontmost=True)

    assert result["success"] is True
    assert sent == [("Terminal", "hello")]
