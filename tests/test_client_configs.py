"""Tests for client request configs (issue #79).

Today the client takes long kwargs lists; defaults live in three places
(Click options, MCP schemas, client method signatures).  The deepening:
domain-shaped dataclasses own defaults; callers pass `params`, not 12 kwargs.
"""

from __future__ import annotations

import httpx

from qluent_cli.client import QluentClient
from qluent_cli.client_configs import InvestigationParams, RcaParams
from qluent_cli.config import QluentConfig
from qluent_cli.dates import DateWindow, DateWindows


def _config() -> QluentConfig:
    return QluentConfig(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )


def _windows() -> DateWindows:
    from datetime import date

    return DateWindows(
        current=DateWindow(date(2026, 3, 9), date(2026, 3, 15)),
        comparison=DateWindow(date(2026, 3, 2), date(2026, 3, 8)),
    )


def _client_with_capture():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json={"warnings": [], "findings": []})

    client = QluentClient(_config())
    client._client = httpx.Client(
        headers={"X-API-Key": "qk_test"},
        timeout=120.0,
        transport=httpx.MockTransport(handler),
    )
    return client, captured


def test_rca_params_defaults_are_canonical():
    p = RcaParams()
    assert p.max_depth == 3
    assert p.max_branching == 2
    assert p.max_segments == 5
    assert p.min_contribution_share == 0.1
    assert p.segment_by == ()
    assert p.filters == {}
    assert p.metric is None


def test_rca_params_overrides_apply():
    p = RcaParams(max_depth=4, segment_by=("region",), filters={"country": ["SE"]})
    assert p.max_depth == 4
    assert p.segment_by == ("region",)
    assert p.filters == {"country": ["SE"]}
    # untouched fields keep defaults
    assert p.max_branching == 2


def test_investigation_params_extends_rca_params():
    p = InvestigationParams(max_depth=4, trend_periods=8, trend_grain="month")
    assert p.max_depth == 4
    assert p.trend_periods == 8
    assert p.trend_grain == "month"
    # Defaults
    assert p.compare_trees == ()


def test_root_cause_tree_accepts_rca_params():
    client, captured = _client_with_capture()
    client.root_cause_tree(
        "revenue",
        windows=_windows(),
        params=RcaParams(
            max_depth=4,
            max_branching=3,
            segment_by=("region",),
            filters={"country": ["SE"]},
        ),
    )
    body = captured["json"]
    assert body["current_window"] == {"date_from": "2026-03-09", "date_to": "2026-03-15"}
    assert body["comparison_window"] == {"date_from": "2026-03-02", "date_to": "2026-03-08"}
    assert body["max_depth"] == 4
    assert body["max_branching"] == 3
    assert body["segment_by"] == ["region"]
    assert body["filters"] == {"country": ["SE"]}


def test_root_cause_tree_default_params_send_canonical_defaults():
    """Calling without params must still send the documented defaults."""
    client, captured = _client_with_capture()
    client.root_cause_tree("revenue", windows=_windows())
    body = captured["json"]
    assert body["max_depth"] == 3
    assert body["max_branching"] == 2
    assert body["max_segments"] == 5
    assert body["min_contribution_share"] == 0.1


def test_investigate_tree_accepts_investigation_params():
    client, captured = _client_with_capture()
    client.investigate_tree(
        "revenue",
        windows=_windows(),
        params=InvestigationParams(
            trend_periods=12,
            trend_grain="month",
            compare_trees=("growth",),
            max_depth=4,
        ),
    )
    body = captured["json"]
    assert body["trend_periods"] == 12
    assert body["trend_grain"] == "month"
    assert body["compare_trees"] == ["growth"]
    assert body["max_depth"] == 4
