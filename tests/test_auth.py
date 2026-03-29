from __future__ import annotations

import threading

import httpx
import pytest

from qluent_cli.auth import (
    CallbackResult,
    _CallbackServer,
    _api_url_to_ui_url,
    _find_free_port,
    browser_login,
)
from qluent_cli import auth as auth_module


def test_find_free_port_returns_valid_port():
    port = _find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def _start_server(state: str) -> tuple[_CallbackServer, int]:
    port = _find_free_port()
    server = _CallbackServer(port, expected_state=state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_callback_success():
    state = "test_state_123"
    server, port = _start_server(state)
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}/callback",
            params={
                "api_key": "qk_test_key",
                "project_uuid": "proj-abc",
                "user_email": "a@b.com",
                "state": state,
            },
        )
        assert resp.status_code == 200
        assert "Logged in" in resp.text

        assert server.got_callback.is_set()
        assert server.result is not None
        assert server.result.success is True
        assert server.result.api_key == "qk_test_key"
        assert server.result.project_uuid == "proj-abc"
        assert server.result.user_email == "a@b.com"
    finally:
        server.shutdown()


def test_callback_state_mismatch():
    server, port = _start_server("correct_state")
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}/callback",
            params={
                "api_key": "qk_test",
                "project_uuid": "proj-abc",
                "user_email": "a@b.com",
                "state": "wrong_state",
            },
        )
        assert resp.status_code == 400
        assert server.result is not None
        assert server.result.success is False
        assert "State mismatch" in server.result.error
    finally:
        server.shutdown()


def test_callback_missing_params():
    state = "ok_state"
    server, port = _start_server(state)
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}/callback",
            params={"state": state, "api_key": "qk_test"},
        )
        assert resp.status_code == 400
        assert server.result is not None
        assert server.result.success is False
        assert "project_uuid" in server.result.error
        assert "user_email" in server.result.error
    finally:
        server.shutdown()


def test_callback_error_from_auth_server():
    state = "ok_state"
    server, port = _start_server(state)
    try:
        resp = httpx.get(
            f"http://127.0.0.1:{port}/callback",
            params={
                "state": state,
                "error": "access_denied",
                "error_description": "User cancelled",
            },
        )
        assert resp.status_code == 400
        assert server.result is not None
        assert server.result.success is False
        assert server.result.error == "User cancelled"
    finally:
        server.shutdown()


def test_callback_wrong_path():
    server, port = _start_server("state")
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/wrong")
        assert resp.status_code == 404
        assert not server.got_callback.is_set()
    finally:
        server.shutdown()


def test_api_url_to_ui_url_production():
    assert _api_url_to_ui_url("https://api.app.qluent.com") == "https://app.qluent.com"


def test_api_url_to_ui_url_production_trailing_slash():
    assert _api_url_to_ui_url("https://api.app.qluent.com/") == "https://app.qluent.com"


def test_api_url_to_ui_url_localhost():
    assert _api_url_to_ui_url("http://localhost:8001") == "http://localhost:5173"


def test_api_url_to_ui_url_127():
    assert _api_url_to_ui_url("http://127.0.0.1:8001") == "http://localhost:5173"


def test_browser_login_timeout(monkeypatch):
    monkeypatch.setattr(auth_module, "LOGIN_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    result = browser_login("http://localhost:8001")

    assert result.success is False
    assert "timed out" in result.error.lower()


def test_browser_login_success_flow(monkeypatch):
    """Simulate a full login flow by having webbrowser.open trigger the callback."""

    def fake_open(url: str) -> bool:
        # Parse the callback_url and state from the login URL
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        callback_url = params["callback_url"][0]
        state = params["state"][0]

        def do_callback():
            httpx.get(
                callback_url,
                params={
                    "api_key": "qk_browser_test",
                    "project_uuid": "proj-browser",
                    "user_email": "browser@test.com",
                    "state": state,
                },
            )

        threading.Thread(target=do_callback, daemon=True).start()
        return True

    monkeypatch.setattr("webbrowser.open", fake_open)

    result = browser_login("http://localhost:8001")

    assert result.success is True
    assert result.api_key == "qk_browser_test"
    assert result.project_uuid == "proj-browser"
    assert result.user_email == "browser@test.com"
