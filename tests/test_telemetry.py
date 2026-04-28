from __future__ import annotations

import threading
from typing import Any

import pytest

from qluent_cli import telemetry


@pytest.fixture(autouse=True)
def _reset_pending_threads() -> None:
    telemetry._pending_threads.clear()


@pytest.fixture()
def _no_env(monkeypatch):
    for var in ("QLUENT_NO_TELEMETRY", "QLUENT_INVOKED_BY", "QLUENT_API_URL", "QLUENT_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_command_from_argv_extracts_group_and_subcommand():
    assert telemetry._command_from_argv(
        ["trees", "evaluate", "--period", "last-month", "tree_id"]
    ) == "trees evaluate"


def test_command_from_argv_handles_top_level_command():
    assert telemetry._command_from_argv(["status"]) == "status"
    assert telemetry._command_from_argv(["status", "--json-output"]) == "status"


def test_command_from_argv_skips_leading_flags():
    assert telemetry._command_from_argv(["--version"]) == ""


def test_command_from_argv_handles_nested_groups():
    assert telemetry._command_from_argv(["claude", "init", "--force"]) == "claude init"
    assert telemetry._command_from_argv(["rca", "analyze"]) == "rca analyze"


def test_track_command_skipped_when_env_opt_out(monkeypatch, isolated_config, _no_env):
    monkeypatch.setenv("QLUENT_NO_TELEMETRY", "1")

    called: dict[str, Any] = {"count": 0}

    def fake_thread(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("thread should not start when opted out")

    monkeypatch.setattr(telemetry.threading, "Thread", fake_thread)

    telemetry.track_command(command="status", duration_ms=12, exit_code=0)

    assert called["count"] == 0


def test_track_command_skipped_when_config_opt_out(monkeypatch, isolated_config, _no_env):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    import json
    config_file.write_text(json.dumps({"telemetry_enabled": False, "api_url": "https://api.example.com"}))

    monkeypatch.setattr(
        telemetry.threading,
        "Thread",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not start")),
    )

    telemetry.track_command(command="status", duration_ms=1, exit_code=0)


def test_track_command_posts_payload(monkeypatch, isolated_config, _no_env):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    import json
    config_file.write_text(
        json.dumps(
            {
                "api_key": "qk_test",
                "api_url": "https://api.example.com",
                "project_uuid": "proj-1",
                "user_email": "u@example.com",
            }
        )
    )

    captured: dict[str, Any] = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout

    monkeypatch.setattr(telemetry.httpx, "post", fake_post)

    class InlineThread:
        def __init__(self, target, args, daemon):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(telemetry.threading, "Thread", InlineThread)

    telemetry.track_command(
        command="trees evaluate",
        duration_ms=42,
        exit_code=0,
    )

    assert captured["url"] == "https://api.example.com/api/v1/telemetry/cli"
    assert captured["headers"] == {"X-API-Key": "qk_test"}
    payload = captured["payload"]
    assert payload["command"] == "trees evaluate"
    assert payload["duration_ms"] == 42
    assert payload["exit_code"] == 0
    assert payload["error_type"] is None
    assert payload["project_uuid"] == "proj-1"
    assert payload["user_email"] == "u@example.com"
    assert payload["invoked_by"] == "cli"
    assert payload["cli_version"]


def test_track_command_records_invoked_by_from_env(monkeypatch, isolated_config, _no_env):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    import json
    config_file.write_text(json.dumps({"api_url": "https://api.example.com"}))

    monkeypatch.setenv("QLUENT_INVOKED_BY", "claude-code-plugin")

    captured: dict[str, Any] = {}

    def fake_post(url, json, headers, timeout):
        captured["payload"] = json

    monkeypatch.setattr(telemetry.httpx, "post", fake_post)

    class InlineThread:
        def __init__(self, target, args, daemon):
            target(*args)

        def start(self):
            return None

        def join(self, timeout=None):
            return None

    monkeypatch.setattr(telemetry.threading, "Thread", InlineThread)

    telemetry.track_command(command="trees list", duration_ms=1, exit_code=0)

    assert captured["payload"]["invoked_by"] == "claude-code-plugin"


def test_track_command_swallows_errors(monkeypatch, isolated_config, _no_env):
    def boom(*_a, **_kw):
        raise RuntimeError("config exploded")

    monkeypatch.setattr(telemetry, "load_raw_config", boom)

    telemetry.track_command(command="status", duration_ms=1, exit_code=0)


def test_post_silently_swallows_network_errors(monkeypatch):
    def fake_post(*_a, **_kw):
        raise httpx_exception()

    def httpx_exception():
        return Exception("network down")

    monkeypatch.setattr(telemetry.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))

    telemetry._post_silently("https://x", {}, {})


def test_track_lifecycle_records_exit_code(monkeypatch, isolated_config, _no_env):
    captured: dict[str, Any] = {}

    def fake_track(*, command, duration_ms, exit_code, error_type=None):
        captured["command"] = command
        captured["exit_code"] = exit_code
        captured["error_type"] = error_type

    monkeypatch.setattr(telemetry, "track_command", fake_track)
    monkeypatch.setattr(telemetry, "flush", lambda timeout=1.0: None)

    with pytest.raises(SystemExit) as exc:
        with telemetry.track_lifecycle(["trees", "evaluate"]):
            raise SystemExit(2)

    assert exc.value.code == 2
    assert captured["command"] == "trees evaluate"
    assert captured["exit_code"] == 2
    assert captured["error_type"] is None


def test_track_lifecycle_records_unhandled_exception(monkeypatch, isolated_config, _no_env):
    captured: dict[str, Any] = {}

    def fake_track(*, command, duration_ms, exit_code, error_type=None):
        captured["exit_code"] = exit_code
        captured["error_type"] = error_type

    monkeypatch.setattr(telemetry, "track_command", fake_track)
    monkeypatch.setattr(telemetry, "flush", lambda timeout=1.0: None)

    with pytest.raises(ValueError):
        with telemetry.track_lifecycle(["status"]):
            raise ValueError("kaboom")

    assert captured["exit_code"] == 1
    assert captured["error_type"] == "ValueError"


def test_track_lifecycle_records_success(monkeypatch, isolated_config, _no_env):
    captured: dict[str, Any] = {}

    def fake_track(*, command, duration_ms, exit_code, error_type=None):
        captured["exit_code"] = exit_code
        captured["duration_ms"] = duration_ms

    monkeypatch.setattr(telemetry, "track_command", fake_track)
    monkeypatch.setattr(telemetry, "flush", lambda timeout=1.0: None)

    with telemetry.track_lifecycle(["status"]):
        pass

    assert captured["exit_code"] == 0
    assert captured["duration_ms"] >= 0


def test_flush_joins_pending_threads(monkeypatch):
    finished: list[bool] = []

    def worker():
        finished.append(True)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    telemetry._pending_threads.append(t)

    telemetry.flush(timeout=1.0)

    assert finished == [True]
