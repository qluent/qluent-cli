from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli
from qluent_cli.query_contracts import QUERY_SCHEMA_VERSION


def _config(**overrides: Any) -> QluentConfig:
    defaults = dict(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )
    defaults.update(overrides)
    return QluentConfig(**defaults)


RESULT_EVENT = {
    "success": True,
    "thread_id": "th_1",
    "message_id": "msg_1",
    "question": "top customers?",
    "explanation": "Acme leads on revenue.",
    "data": [
        {"customer": "Acme", "revenue": 120340},
        {"customer": "Globex", "revenue": 98110},
    ],
    "columns": ["customer", "revenue"],
    "row_count": 2,
    "download_url": "https://example.com/dl",
    "google_sheets_url": None,
}


class FakeStreamingClient:
    """Streams a canned event sequence; records constructor + call args."""

    events: list[tuple[str, dict[str, Any]]] = []
    calls: list[dict[str, Any]] = []

    def __init__(self, config: QluentConfig) -> None:
        self.config = config

    def iter_query_events(self, question: str, *, thread_id: str | None = None):
        type(self).calls.append({"question": question, "thread_id": thread_id})
        yield from type(self).events

    def query(self, question: str, *, thread_id: str | None = None, progress_callback=None):
        type(self).calls.append(
            {"question": question, "thread_id": thread_id, "sync": True}
        )
        raise AssertionError("sync path should not be used in this test")


def _wire(monkeypatch, client_cls, config: QluentConfig | None = None) -> None:
    monkeypatch.setattr("qluent_cli.query.load_config", lambda: config or _config())
    monkeypatch.setattr("qluent_cli.query.QluentClient", client_cls)
    client_cls.calls = []


def test_query_streaming_success_renders_human_output(monkeypatch, isolated_config):
    FakeStreamingClient.events = [
        ("status", {"message": "Generating SQL", "stage": "sql_generation"}),
        ("sql", {"sql": "SELECT customer, revenue FROM t"}),
        ("result", dict(RESULT_EVENT)),
    ]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "top customers?"])

    assert result.exit_code == 0, result.output
    assert "Acme leads on revenue." in result.output
    assert "customer" in result.output
    assert "Acme" in result.output
    assert "SQL: SELECT customer, revenue FROM t" in result.output
    assert "Download: https://example.com/dl" in result.output
    assert "Thread: th_1" in result.output
    assert "--thread th_1" in result.output
    assert "run_id:" in result.output


def test_query_streaming_persists_run(monkeypatch, isolated_config):
    FakeStreamingClient.events = [("result", dict(RESULT_EVENT))]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "top customers?"])
    assert result.exit_code == 0, result.output

    from qluent_cli import sessions

    record = sessions.find_last_run(command=sessions.QUERY_COMMAND)
    assert record is not None
    assert record.tree_id is None
    stored = record.load()
    assert stored["args"]["question"] == "top customers?"
    assert stored["result"]["schema_version"] == QUERY_SCHEMA_VERSION


def test_query_json_output_emits_contract(monkeypatch, isolated_config):
    FakeStreamingClient.events = [
        ("sql", {"sql": "SELECT 1"}),
        ("result", dict(RESULT_EVENT)),
    ]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "top customers?", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == QUERY_SCHEMA_VERSION
    assert payload["status"] == "ok"
    assert payload["deterministic"] is False
    assert payload["sql"] == "SELECT 1"
    assert payload["answer"] == "Acme leads on revenue."


def test_query_clarification_renders_options_and_exits_zero(
    monkeypatch, isolated_config
):
    FakeStreamingClient.events = [
        (
            "clarification",
            {
                "success": False,
                "thread_id": "th_9",
                "message_id": "msg_9",
                "question": "revenue?",
                "message": "Which revenue do you mean?",
                "options": ["Gross revenue", "Net revenue"],
            },
        ),
    ]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "revenue?"])

    assert result.exit_code == 0, result.output
    assert "Clarification needed:" in result.output
    assert "Which revenue do you mean?" in result.output
    assert "1. Gross revenue" in result.output
    assert "--thread th_9" in result.output


def test_query_error_event_exits_nonzero_with_code(monkeypatch, isolated_config):
    FakeStreamingClient.events = [
        ("error", {"success": False, "error_code": "EXECUTION_ERROR", "error": "boom"}),
    ]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "q"])

    assert result.exit_code != 0
    assert "EXECUTION_ERROR: boom" in result.output


def test_query_thread_option_is_forwarded(monkeypatch, isolated_config):
    FakeStreamingClient.events = [("result", dict(RESULT_EVENT))]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "follow up", "--thread", "th_1"])

    assert result.exit_code == 0, result.output
    assert FakeStreamingClient.calls[0]["thread_id"] == "th_1"


def test_query_sync_flag_uses_sync_endpoint(monkeypatch, isolated_config):
    class FakeSyncClient:
        calls: list[dict[str, Any]] = []

        def __init__(self, config: QluentConfig) -> None:
            pass

        def iter_query_events(self, *args: Any, **kwargs: Any):
            raise AssertionError("streaming path should not be used with --sync")

        def query(self, question, *, thread_id=None, progress_callback=None):
            type(self).calls.append({"question": question, "thread_id": thread_id})
            raw = dict(RESULT_EVENT)
            raw["sql"] = "SELECT 3"
            return raw

    _wire(monkeypatch, FakeSyncClient)

    result = CliRunner().invoke(cli, ["query", "q", "--sync"])

    assert result.exit_code == 0, result.output
    assert FakeSyncClient.calls == [{"question": "q", "thread_id": None}]
    assert "SQL: SELECT 3" in result.output


def test_query_falls_back_to_sync_when_stream_unsupported(
    monkeypatch, isolated_config
):
    from qluent_cli.client import QueryStreamUnsupported

    class FakeFallbackClient:
        calls: list[str] = []

        def __init__(self, config: QluentConfig) -> None:
            pass

        def iter_query_events(self, question, *, thread_id=None):
            type(self).calls.append("stream")
            raise QueryStreamUnsupported()
            yield  # pragma: no cover

        def query(self, question, *, thread_id=None, progress_callback=None):
            type(self).calls.append("sync")
            return dict(RESULT_EVENT)

    _wire(monkeypatch, FakeFallbackClient)

    result = CliRunner().invoke(cli, ["query", "q"])

    assert result.exit_code == 0, result.output
    assert FakeFallbackClient.calls == ["stream", "sync"]
    assert "Acme leads on revenue." in result.output


def test_query_truncation_footer_shown_for_large_row_counts(
    monkeypatch, isolated_config
):
    big = dict(RESULT_EVENT)
    big["data"] = [{"customer": f"c{i}", "revenue": i} for i in range(30)]
    big["row_count"] = 4200
    FakeStreamingClient.events = [("result", big)]
    _wire(monkeypatch, FakeStreamingClient)

    result = CliRunner().invoke(cli, ["query", "all customers"])

    assert result.exit_code == 0, result.output
    assert "showing 20 of 4,200 rows" in result.output


def test_query_client_safe_hides_sql_in_human_output(monkeypatch, isolated_config):
    FakeStreamingClient.events = [
        ("sql", {"sql": "SELECT secret FROM t"}),
        ("result", dict(RESULT_EVENT)),
    ]
    _wire(monkeypatch, FakeStreamingClient, config=_config(client_safe=True))

    result = CliRunner().invoke(cli, ["query", "q"])

    assert result.exit_code == 0, result.output
    assert "SELECT secret" not in result.output

    # JSON output keeps the SQL and flags client-safe mode for agents.
    FakeStreamingClient.events = [
        ("sql", {"sql": "SELECT secret FROM t"}),
        ("result", dict(RESULT_EVENT)),
    ]
    result = CliRunner().invoke(cli, ["query", "q", "--json-output"])
    payload = json.loads(result.stdout)
    assert payload["sql"] == "SELECT secret FROM t"
    assert payload["project_context"]["client_safe"] is True


def test_runs_list_accepts_query_command_filter(monkeypatch, isolated_config):
    FakeStreamingClient.events = [("result", dict(RESULT_EVENT))]
    _wire(monkeypatch, FakeStreamingClient)

    assert CliRunner().invoke(cli, ["query", "q"]).exit_code == 0

    result = CliRunner().invoke(
        cli, ["runs", "list", "--command", "query", "--json-output"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["command"] == "query"
