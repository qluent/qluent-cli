from __future__ import annotations

from qluent_cli.client import QluentClient
from qluent_cli.config import QluentConfig


def test_client_safe_mode_adds_redaction_header(monkeypatch):
    captured: dict[str, object] = {}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout):
            captured["headers"] = headers
            captured["timeout"] = timeout

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
        def __init__(self, *, headers, timeout):
            captured["headers"] = headers
            captured["timeout"] = timeout

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
        def __init__(self, *, headers, timeout):
            captured["headers"] = headers
            captured["timeout"] = timeout

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
        def __init__(self, *, headers, timeout):
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

    result = client.root_cause_tree(
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
        def __init__(self, *, headers, timeout):
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
