from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli


def test_trees_validate_formats_contract_diagnostics(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_validate_tree(self, tree_id):
        assert tree_id == "revenue"
        return {
            "tree_id": "revenue",
            "tree_label": "Revenue",
            "valid": False,
            "dimensions_declared": ["channel", "country"],
            "supported_dimensions": ["country"],
            "leaf_nodes": [
                {
                    "node_id": "orders",
                    "label": "Orders",
                    "metric_id": 1,
                    "projection_status": "explicit",
                    "projected_columns": ["channel", "day", "value"],
                    "missing_columns": [],
                    "missing_dimensions": ["country"],
                }
            ],
            "errors": [
                "Leaf node 'orders' does not project declared dimensions: country."
            ],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.validate_tree", mock_validate_tree)

    result = CliRunner().invoke(cli, ["trees", "validate", "revenue"])

    assert result.exit_code == 0
    assert "Revenue Validation" in result.output
    assert "Status: invalid" in result.output
    assert "Supported dimensions: country" in result.output
    assert "missing dimensions: country" in result.output
    assert "Leaf node 'orders' does not project declared dimensions: country." in result.output


def test_trees_get_formats_redacted_tree(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
            client_safe=True,
        ),
    )

    def mock_get_tree(self, tree_id):
        assert tree_id == "revenue"
        return {
            "id": "revenue",
            "label": "Revenue",
            "root_node_id": "revenue",
            "redacted": True,
            "redaction_reason": "Client-safe mode hides formulas and execution details.",
            "nodes": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "kind": "formula",
                    "children": ["orders", "aov"],
                    "redacted": True,
                },
                {"id": "orders", "label": "Orders", "kind": "sql_metric", "redacted": True},
                {"id": "aov", "label": "AOV", "kind": "sql_metric", "redacted": True},
            ],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.get_tree", mock_get_tree)

    result = CliRunner().invoke(cli, ["trees", "get", "revenue"])

    assert result.exit_code == 0
    assert "Revenue" in result.output
    assert "Client-safe mode hides formulas and execution details." in result.output
    assert "Revenue [formula]" in result.output
    assert "Orders [sql]" in result.output


def test_trees_validate_formats_redacted_contract_diagnostics(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
            client_safe=True,
        ),
    )

    def mock_validate_tree(self, tree_id):
        assert tree_id == "revenue"
        return {
            "tree_id": "revenue",
            "tree_label": "Revenue",
            "valid": False,
            "redacted": True,
            "redaction_reason": "Client-safe mode redacted SQL contract details.",
            "dimensions_declared": ["channel", "country"],
            "supported_dimensions": ["country"],
            "leaf_nodes": [
                {
                    "node_id": "orders",
                    "label": "Orders",
                    "projection_status": "explicit",
                    "projected_columns": [],
                    "missing_columns": [],
                    "missing_dimensions": ["country"],
                }
            ],
            "errors": [
                "One or more leaf nodes do not project all declared dimensions."
            ],
            "warnings": ["Client-safe mode redacted SQL contract details."],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.validate_tree", mock_validate_tree)

    result = CliRunner().invoke(cli, ["trees", "validate", "revenue"])

    assert result.exit_code == 0
    assert "Revenue Validation" in result.output
    assert "Client-safe mode redacted SQL contract details." in result.output
    assert "[metric" not in result.output
    assert "columns:" not in result.output
    assert "missing dimensions: country" in result.output


def test_trees_levers_outputs_ranked_scenarios(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_evaluate_tree(self, tree_id, current_from, current_to, comparison_from, comparison_to):
        assert tree_id == "revenue"
        assert current_from == "2026-03-09"
        assert current_to == "2026-03-15"
        assert comparison_from == "2026-03-02"
        assert comparison_to == "2026-03-08"
        return {
            "tree_id": "revenue",
            "tree_label": "Revenue",
            "root_node_id": "revenue",
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 1000,
            "comparison_value": 900,
            "delta_value": 100,
            "delta_ratio": 0.1111111111,
            "top_contributors": [],
            "nodes": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "kind": "formula",
                    "current_value": 1000,
                    "comparison_value": 900,
                    "delta_value": 100,
                    "delta_ratio": 0.1111111111,
                    "contributions": [],
                    "sensitivity": 1.0,
                    "elasticity": 1.0,
                },
                {
                    "id": "orders",
                    "label": "Orders",
                    "kind": "sql_metric",
                    "current_value": 100,
                    "comparison_value": 90,
                    "delta_value": 10,
                    "delta_ratio": 0.1111111111,
                    "contributions": [],
                    "sensitivity": 10.0,
                    "elasticity": 1.2,
                },
                {
                    "id": "aov",
                    "label": "AOV",
                    "kind": "sql_metric",
                    "current_value": 10,
                    "comparison_value": 10,
                    "delta_value": 0,
                    "delta_ratio": 0.0,
                    "contributions": [],
                    "sensitivity": 100.0,
                    "elasticity": 0.8,
                },
                {
                    "id": "spend",
                    "label": "Spend",
                    "kind": "sql_metric",
                    "current_value": 250,
                    "comparison_value": 240,
                    "delta_value": 10,
                    "delta_ratio": 0.0416666667,
                    "contributions": [],
                    "sensitivity": -4.0,
                    "elasticity": -0.6,
                },
            ],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.evaluate_tree", mock_evaluate_tree)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "levers",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--scenario",
            "0.02",
            "--scenario",
            "0.1",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tree_id"] == "revenue"
    assert payload["scenarios"] == [0.02, 0.1]
    assert [lever["node_id"] for lever in payload["top_levers"]] == [
        "orders",
        "aov",
        "spend",
    ]
    assert payload["top_levers"][0]["recommended_direction"] == "increase"
    assert payload["top_levers"][2]["recommended_direction"] == "decrease"
    assert payload["top_levers"][0]["scenario_impacts"][0] == {
        "node_change_ratio": 0.02,
        "estimated_root_delta_ratio": 0.024,
        "estimated_root_delta_value": 24.0,
    }
    assert "local linear estimates" in payload["warnings"][-1]


def test_trees_evaluate_contract_output_includes_value_metadata(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_evaluate_tree(self, tree_id, current_from, current_to, comparison_from, comparison_to):
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "root_node_id": "revenue",
            "unit": "USD",
            "grain": "day",
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 120,
            "comparison_value": 100,
            "delta_value": 20,
            "delta_ratio": 0.2,
            "top_contributors": [{"node_id": "orders", "delta_value": 20}],
            "nodes": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "kind": "formula",
                    "unit": "USD",
                    "grain": "day",
                    "current_value": 120,
                    "comparison_value": 100,
                    "delta_value": 20,
                    "delta_ratio": 0.2,
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.evaluate_tree", mock_evaluate_tree)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "evaluate",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--contract-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "qluent.tree_query.v1"
    assert payload["deterministic"] is True
    assert payload["agent_interpretation"] is None
    assert payload["windows"]["current_day_count"] == 7
    metric_value = payload["metric_values"][0]
    assert metric_value["current"]["unit"] == "USD"
    assert metric_value["current"]["grain"] == "day"
    assert metric_value["current"]["provenance"]["source"] == "metric_tree_evaluate"
    assert metric_value["delta"]["current_window"]["date_from"] == "2026-03-09"


def test_trees_levers_formats_human_output(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_evaluate_tree(self, tree_id, current_from, current_to, comparison_from, comparison_to):
        return {
            "tree_id": "roas",
            "tree_label": "ROAS",
            "root_node_id": "roas",
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 50,
            "comparison_value": 40,
            "delta_value": 10,
            "delta_ratio": 0.25,
            "top_contributors": [],
            "nodes": [
                {
                    "id": "roas",
                    "label": "ROAS",
                    "kind": "formula",
                    "current_value": 50,
                    "comparison_value": 40,
                    "delta_value": 10,
                    "delta_ratio": 0.25,
                    "contributions": [],
                    "sensitivity": 1.0,
                    "elasticity": 1.0,
                },
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "kind": "sql_metric",
                    "current_value": 1000,
                    "comparison_value": 900,
                    "delta_value": 100,
                    "delta_ratio": 0.1111111111,
                    "contributions": [],
                    "sensitivity": 0.05,
                    "elasticity": 1.1,
                },
                {
                    "id": "spend",
                    "label": "Spend",
                    "kind": "sql_metric",
                    "current_value": 20,
                    "comparison_value": 22.5,
                    "delta_value": -2.5,
                    "delta_ratio": -0.1111111111,
                    "contributions": [],
                    "sensitivity": -2.5,
                    "elasticity": -0.9,
                },
            ],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.evaluate_tree", mock_evaluate_tree)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "levers",
            "roas",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
        ],
    )

    assert result.exit_code == 0
    assert "ROAS Levers" in result.output
    assert "best action: decrease" in result.output
    assert "+5% node → root" in result.output


def test_trees_investigate_delegates_to_server(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    investigate_calls: list[dict] = []

    def mock_investigate_tree(
        self, tree_id, c_from, c_to, p_from, p_to, **kwargs
    ):
        investigate_calls.append({"tree_id": tree_id, "c_from": c_from, **kwargs})
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "current_window": {"date_from": c_from, "date_to": c_to},
            "comparison_window": {"date_from": p_from, "date_to": p_to},
            "validation": {"valid": True, "supported_dimensions": ["channel", "country"]},
            "trend": {"evaluations": []},
            "evaluation": {"tree_id": tree_id, "current_value": 100, "comparison_value": 90},
            "root_cause": {"conclusion": None},
            "agent": {
                "status": "resolved",
                "top_findings": ["Revenue grew 11%"],
                "gaps": [],
                "recommended_next_steps": [],
            },
        }

    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.investigate_tree", mock_investigate_tree
    )

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "investigate",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--trend-periods",
            "2",
            "--compare-tree",
            "orders",
            "--filter",
            "country=SE",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tree_id"] == "revenue"
    assert payload["agent"]["status"] == "resolved"
    assert len(investigate_calls) == 1
    assert investigate_calls[0]["tree_id"] == "revenue"
    assert investigate_calls[0]["compare_trees"] == ["orders"]
    assert investigate_calls[0]["filters"] == {"country": ["SE"]}


def test_trees_investigate_requires_tree_id():
    result = CliRunner().invoke(cli, ["trees", "investigate"])

    assert result.exit_code != 0
    assert "TREE_ID" in result.output or "tree_id" in result.output.lower()


def test_trees_match_subcommand_removed():
    result = CliRunner().invoke(cli, ["trees", "match", "any question"])

    assert result.exit_code != 0
    assert "no such command" in result.output.lower()
