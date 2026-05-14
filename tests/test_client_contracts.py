"""Tests for client-boundary contract enrichment.

The deepening goal (issue #80): `client.root_cause_tree(...)` must return an
enriched RCA contract by construction, not raw API data.  Callers cannot
forget to enrich because the client owns the contract.
"""

from __future__ import annotations

import httpx
import pytest

from qluent_cli.client import QluentClient
from qluent_cli.config import QluentConfig
from qluent_cli.rca_contracts import RCA_SCHEMA_VERSION


def _client_with_mock_transport(handler) -> QluentClient:
    config = QluentConfig(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )
    client = QluentClient(config)
    client._client = httpx.Client(
        headers={"X-API-Key": "qk_test"},
        timeout=120.0,
        transport=httpx.MockTransport(handler),
    )
    return client


def _raw_rca_response() -> dict:
    return {
        "tree_label": "Revenue",
        "tree_id": "revenue",
        "root_node_id": "revenue",
        "current_window": {"date_from": "2026-03-09", "date_to": "2026-03-15"},
        "comparison_window": {"date_from": "2026-03-02", "date_to": "2026-03-08"},
        "current_value": 900,
        "comparison_value": 1000,
        "delta_value": -100,
        "delta_ratio": -0.1,
        "findings": [
            {
                "node_id": "orders",
                "label": "Orders",
                "depth": 1,
                "path": ["revenue", "orders"],
                "current_value": 100,
                "comparison_value": 80,
                "delta_value": 20,
                "delta_ratio": 0.25,
                "contribution_value": 35,
                "contribution_share": 0.5,
            }
        ],
        "warnings": [],
    }


def test_root_cause_tree_returns_enriched_contract():
    """The public method must add schema_version, provenance, and
    materiality fields — callers cannot forget."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_raw_rca_response())

    client = _client_with_mock_transport(handler)
    result = client.root_cause_tree(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )

    assert result["schema_version"] == RCA_SCHEMA_VERSION
    assert result["contract_kind"] == "deterministic_rca"
    assert result["deterministic"] is True
    assert result["provenance"]["source"] == "metric_tree_root_cause"
    assert result["provenance"]["project_uuid"] == "project-123"
    # findings get materiality stamped on
    assert result["findings"][0]["share_of_parent_delta"] == 0.5


def test_root_cause_tree_enrichment_uses_clients_own_config():
    """Enrichment pulls project_uuid from the client, not from a caller."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_raw_rca_response())

    client = _client_with_mock_transport(handler)
    result = client.root_cause_tree(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )
    assert result["provenance"]["project_uuid"] == "project-123"
    assert result["provenance"]["tree_id"] == "revenue"


def test_root_cause_tree_enrichment_does_not_double_apply():
    """If the upstream API ever returns a partially-enriched payload, the
    client should land at a coherent enriched shape, not stack twice."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _raw_rca_response()
        payload["schema_version"] = "qluent.rca.v1"
        return httpx.Response(200, json=payload)

    client = _client_with_mock_transport(handler)
    result = client.root_cause_tree(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )
    assert result["schema_version"] == "qluent.rca.v1"
    # Provenance still set exactly once.
    assert isinstance(result["provenance"], dict)


def test_investigate_tree_accepts_optional_analysis_run_uuid():
    """The investigate response is a passthrough contract; new backend handles
    must survive client parsing unchanged."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tree_id": "revenue",
                "analysis_run_uuid": "9f7d8d21-1e04-43a8-a33e-2cf7d22d2c2b",
                "agent": {"status": "resolved"},
            },
        )

    client = _client_with_mock_transport(handler)
    result = client.investigate_tree(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )

    assert result["analysis_run_uuid"] == "9f7d8d21-1e04-43a8-a33e-2cf7d22d2c2b"


def test_investigate_tree_accepts_legacy_response_without_analysis_run_uuid():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"tree_id": "revenue", "agent": {}})

    client = _client_with_mock_transport(handler)
    result = client.investigate_tree(
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )

    assert result["tree_id"] == "revenue"
    assert "analysis_run_uuid" not in result
