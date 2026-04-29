from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.elasticity import analyze_elasticity
from qluent_cli.main import cli


class _StubClient:
    def __init__(self, payload):
        self.payload = payload
        self.captured = {}

    def elasticity_tree(
        self,
        tree_id,
        current_from=None,
        current_to=None,
        comparison_from=None,
        comparison_to=None,
        *,
        windows=None,
        params=None,
        outcome=None,
        lever=None,
        dimension=None,
        filters=None,
    ):
        if windows is not None:
            current_from, current_to, comparison_from, comparison_to = windows.iso_tuple()
        if params is not None:
            outcome = outcome or params.outcome
            lever = lever or params.lever
            dimension = dimension if dimension is not None else params.dimension
            filters = filters if filters is not None else dict(params.filters)
        self.captured = {
            "tree_id": tree_id,
            "current_from": current_from,
            "current_to": current_to,
            "comparison_from": comparison_from,
            "comparison_to": comparison_to,
            "outcome": outcome,
            "lever": lever,
            "dimension": dimension,
            "filters": filters,
        }
        return dict(self.payload)


def test_analyze_elasticity_stamps_contract_defaults_without_click():
    config = QluentConfig(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )
    client = _StubClient({"results": [{"segment": "Nordics", "elasticity": 0.3}]})

    data = analyze_elasticity(
        client,
        config,
        tree_id="revenue",
        outcome="net_revenue",
        lever="voucher_cost",
        dimension="region",
        current_from="2026-03-01",
        current_to="2026-03-31",
        comparison_from="2026-02-01",
        comparison_to="2026-02-28",
        filters={"country": ["SE"]},
    )

    assert client.captured["filters"] == {"country": ["SE"]}
    assert client.captured["dimension"] == "region"
    assert data["contract_kind"] == "elasticity_analysis"
    assert data["deterministic"] is True
    assert data["evidence_type"] == "observed_correlation"
    assert data["warnings"] == []
    assert data["current_window"] == {"date_from": "2026-03-01", "date_to": "2026-03-31"}
    assert data["comparison_window"] == {"date_from": "2026-02-01", "date_to": "2026-02-28"}
    assert data["provenance"] == {
        "source": "metric_tree_elasticity",
        "project_uuid": "project-123",
        "tree_id": "revenue",
        "outcome": "net_revenue",
        "lever": "voucher_cost",
    }


def test_analyze_elasticity_does_not_overwrite_server_provided_fields():
    config = QluentConfig(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )
    client = _StubClient(
        {
            "evidence_type": "experimental",
            "warnings": ["server-issued warning"],
            "provenance": {"source": "server-override"},
        }
    )

    data = analyze_elasticity(
        client,
        config,
        tree_id="revenue",
        outcome="net_revenue",
        lever="voucher_cost",
        current_from="2026-03-01",
        current_to="2026-03-31",
        comparison_from="2026-02-01",
        comparison_to="2026-02-28",
    )

    assert data["evidence_type"] == "experimental"
    assert data["warnings"] == ["server-issued warning"]
    assert data["provenance"] == {"source": "server-override"}


def test_elasticity_command_outputs_agent_ready_json(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.elasticity.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_elasticity_tree(
        self,
        tree_id,
        current_from=None,
        current_to=None,
        comparison_from=None,
        comparison_to=None,
        *,
        windows=None,
        params=None,
        outcome=None,
        lever=None,
        dimension=None,
        filters=None,
    ):
        if windows is not None:
            current_from, current_to, comparison_from, comparison_to = windows.iso_tuple()
        if params is not None:
            outcome = outcome or params.outcome
            lever = lever or params.lever
            dimension = dimension if dimension is not None else params.dimension
            filters = filters if filters is not None else dict(params.filters)
        assert tree_id == "revenue"
        assert outcome == "net_revenue"
        assert lever == "voucher_cost"
        assert dimension == "region"
        assert filters == {"country": ["SE"]}
        return {
            "tree_label": "Revenue",
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "evidence_type": "observed_correlation",
            "confidence": "low",
            "results": [
                {
                    "segment": "Nordics",
                    "elasticity": 0.3,
                    "confidence": "low",
                    "low_confidence": True,
                }
            ],
            "warnings": ["Observed correlation only; do not describe as causal."],
        }

    monkeypatch.setattr("qluent_cli.elasticity.QluentClient.elasticity_tree", mock_elasticity_tree)

    result = CliRunner().invoke(
        cli,
        [
            "elasticity",
            "revenue",
            "--outcome",
            "net_revenue",
            "--lever",
            "voucher_cost",
            "--dimension",
            "region",
            "--current",
            "2026-03-01:2026-03-31",
            "--compare",
            "2026-02-01:2026-02-28",
            "--filter",
            "country=SE",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["contract_kind"] == "elasticity_analysis"
    assert payload["deterministic"] is True
    assert payload["evidence_type"] == "observed_correlation"
    assert payload["results"][0]["low_confidence"] is True
    assert payload["provenance"]["source"] == "metric_tree_elasticity"
