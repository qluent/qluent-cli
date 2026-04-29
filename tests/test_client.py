from __future__ import annotations

import click
import httpx
import pytest

from qluent_cli.client import QluentClient, _RetryTransport
from qluent_cli.config import QluentConfig


def test_client_safe_mode_adds_redaction_header(monkeypatch):
    captured: dict[str, object] = {}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout, transport=None):
            captured["headers"] = headers
            captured["timeout"] = timeout
            captured["transport"] = transport

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)

    QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
            client_safe=True,
        )
    )

    assert captured["headers"] == {
        "X-API-Key": "qk_test",
        "X-Qluent-Client-Safe": "true",
    }


def test_api_key_sets_header(monkeypatch):
    captured: dict[str, object] = {}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout, transport=None):
            captured["headers"] = headers
            captured["timeout"] = timeout
            captured["transport"] = transport

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)

    QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        )
    )

    assert captured["headers"] == {"X-API-Key": "qk_test"}
    assert "Authorization" not in captured["headers"]


def test_no_auth_header_when_both_empty(monkeypatch):
    captured: dict[str, object] = {}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout, transport=None):
            captured["headers"] = headers
            captured["timeout"] = timeout
            captured["transport"] = transport

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)

    QluentClient(
        QluentConfig(
            api_key="",
            api_url="http://localhost:8001",
            project_uuid="project-123",
            user_email="user@example.com",
        )
    )

    assert "X-API-Key" not in captured["headers"]
    assert "Authorization" not in captured["headers"]


def test_base_url_uses_projects_path(monkeypatch):
    monkeypatch.setattr("qluent_cli.client.httpx.Client", lambda **kw: None)

    client = QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        )
    )

    assert client._base == "https://api.example.com/api/v1/project/project-123"


def test_root_cause_tree_sends_metric_when_provided(monkeypatch):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout, transport=None):
            pass

        def post(self, url, *, json):
            captured["url"] = url
            captured["json"] = json
            return DummyResponse()

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)
    client = QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        )
    )

    result = client._root_cause_raw(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
        metric="net_revenue",
        segment_by=["region"],
        filters={"country": ["SE"]},
    )

    assert result == {"ok": True}
    assert (
        captured["url"]
        == "https://api.example.com/api/v1/project/project-123/metric-trees/revenue/root-cause/"
    )
    assert captured["json"]["metric"] == "net_revenue"
    assert captured["json"]["segment_by"] == ["region"]
    assert captured["json"]["filters"] == {"country": ["SE"]}


def test_elasticity_tree_sends_selected_outcome_lever_and_dimension(monkeypatch):
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout, transport=None):
            pass

        def post(self, url, *, json):
            captured["url"] = url
            captured["json"] = json
            return DummyResponse()

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)
    client = QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        )
    )

    result = client.elasticity_tree(
        "revenue",
        "2026-03-01",
        "2026-03-31",
        "2026-02-01",
        "2026-02-28",
        outcome="net_revenue",
        lever="voucher_cost",
        dimension="region",
        filters={"country": ["SE"]},
    )

    assert result == {"ok": True}
    assert (
        captured["url"]
        == "https://api.example.com/api/v1/project/project-123/metric-trees/revenue/elasticity/"
    )
    assert captured["json"]["outcome"] == "net_revenue"
    assert captured["json"]["lever"] == "voucher_cost"
    assert captured["json"]["dimension"] == "region"
    assert captured["json"]["filters"] == {"country": ["SE"]}


# ---------------------------------------------------------------------------
# Retry transport
# ---------------------------------------------------------------------------


def _make_retry_client(handler, *, sleeps, log_calls):
    transport = _RetryTransport(
        httpx.MockTransport(handler),
        backoff=(0.5, 1.5, 4.0),
        sleep=sleeps.append,
        log=lambda *a: log_calls.append(a),
        jitter=lambda x: x,
    )
    return httpx.Client(transport=transport)


def test_retry_get_502_then_success():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert len(calls) == 3
    assert sleeps == [0.5, 1.5]
    assert [l[2] for l in logs] == ["502", "502"]


def test_retry_get_502_exhausts_attempts():
    def handler(request):
        return httpx.Response(502)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 502
    assert len(sleeps) == 3
    assert [l[0] for l in logs] == [1, 2, 3]


def test_retry_post_status_code_not_retried():
    """POST must not be replayed once the server has responded — even on 502."""
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(502)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.post("https://api.example.com/investigate", json={})
    assert resp.status_code == 502
    assert len(calls) == 1
    assert sleeps == []
    assert logs == []


def test_retry_post_connect_error_is_retried():
    """POST must be retried on connect errors — no bytes were sent."""
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.post("https://api.example.com/investigate", json={})
    assert resp.status_code == 200
    assert len(calls) == 2
    assert sleeps == [0.5]
    assert logs[0][2] == "ConnectError"


def test_retry_get_read_timeout_is_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 200
    assert len(calls) == 2


def test_retry_post_read_timeout_not_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    with pytest.raises(httpx.ReadTimeout):
        client.post("https://api.example.com/investigate", json={})
    assert len(calls) == 1
    assert sleeps == []
    assert logs == []


def test_retry_post_remote_protocol_error_not_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        raise httpx.RemoteProtocolError("server disconnected", request=request)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    with pytest.raises(httpx.RemoteProtocolError):
        client.post("https://api.example.com/investigate", json={})
    assert len(calls) == 1
    assert sleeps == []
    assert logs == []


def test_retry_connect_error_exhausts_then_raises():
    def handler(request):
        raise httpx.ConnectError("nope", request=request)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    with pytest.raises(httpx.ConnectError):
        client.get("https://api.example.com/trees")
    assert len(sleeps) == 3


def test_retry_401_not_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 401
    assert len(calls) == 1
    assert sleeps == []


def test_retry_403_not_retried():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403)

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 403
    assert len(calls) == 1


def test_retry_after_header_is_honored():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "30"})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 200
    assert sleeps == [30.0]


def test_retry_after_header_503_honored():
    def handler(request):
        return httpx.Response(503, headers={"Retry-After": "2"})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 503
    assert sleeps == [2.0, 2.0, 2.0]


def test_retry_after_invalid_falls_back_to_backoff():
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "not-a-number"})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    logs: list[tuple] = []
    client = _make_retry_client(handler, sleeps=sleeps, log_calls=logs)

    resp = client.get("https://api.example.com/trees")
    assert resp.status_code == 200
    assert sleeps == [0.5]


def test_retry_log_format_to_stderr(capsys, monkeypatch):
    monkeypatch.delenv("QLUENT_QUIET", raising=False)
    from qluent_cli.client import _default_log

    _default_log(2, 3, "502", 1.5)
    err = capsys.readouterr().err
    assert err == "[qluent] retry 2/3 after 502 in 1.5s\n"


def test_retry_log_suppressed_by_quiet_env(capsys, monkeypatch):
    monkeypatch.setenv("QLUENT_QUIET", "1")
    from qluent_cli.client import _default_log

    _default_log(1, 3, "502", 0.5)
    assert capsys.readouterr().err == ""


def test_retry_log_suppressed_by_click_quiet(capsys, monkeypatch):
    monkeypatch.delenv("QLUENT_QUIET", raising=False)
    from qluent_cli.client import _default_log

    with click.Context(click.Command("qluent"), obj={"quiet": True}):
        _default_log(1, 3, "502", 0.5)
    assert capsys.readouterr().err == ""
