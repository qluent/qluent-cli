from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli


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
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        *,
        outcome,
        lever,
        dimension,
        filters,
    ):
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
