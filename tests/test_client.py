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
