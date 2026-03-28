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


def test_api_key_takes_precedence_over_bearer_token(monkeypatch):
    captured: dict[str, object] = {}

    class DummyHttpxClient:
        def __init__(self, *, headers, timeout):
            captured["headers"] = headers
            captured["timeout"] = timeout

    monkeypatch.setattr("qluent_cli.client.httpx.Client", DummyHttpxClient)

    QluentClient(
        QluentConfig(
            api_key="qk_test",
            api_url="http://localhost:8001",
            project_uuid="project-123",
            user_email="user@example.com",
            bearer_token="jwt_token_here",
        )
    )

    assert captured["headers"]["X-API-Key"] == "qk_test"
    assert "Authorization" not in captured["headers"]


def test_api_key_used_when_no_bearer_token(monkeypatch):
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
