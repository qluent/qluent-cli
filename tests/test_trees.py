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


def test_trees_match_selects_best_tree_and_infers_windows(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_list_trees(self):
        return {
            "trees": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "description": "Total revenue from completed orders",
                    "dimensions": ["channel", "country"],
                    "nodes": [{"id": "orders", "label": "Orders", "kind": "sql_metric"}],
                },
                {
                    "id": "orders",
                    "label": "Orders",
                    "description": "Completed order count",
                    "dimensions": ["channel"],
                    "nodes": [{"id": "orders", "label": "Orders", "kind": "sql_metric"}],
                },
            ]
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.list_trees", mock_list_trees)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "match",
            "Why did revenue drop from 2026-03-09 to 2026-03-15 compared with 2026-03-02 to 2026-03-08?",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["matched"] is True
    assert payload["decision"] == "matched"
    assert payload["tree_id"] == "revenue"
    assert payload["current_window"] == {
        "date_from": "2026-03-09",
        "date_to": "2026-03-15",
    }
    assert payload["comparison_window"] == {
        "date_from": "2026-03-02",
        "date_to": "2026-03-08",
    }


def test_trees_match_reports_ambiguous_candidates(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_list_trees(self):
        return {
            "trees": [
                {"id": "revenue", "label": "Revenue", "nodes": []},
                {"id": "orders", "label": "Orders", "nodes": []},
            ]
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.list_trees", mock_list_trees)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "match",
            "Compare revenue and orders",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["matched"] is False
    assert payload["decision"] == "ambiguous"
    assert [candidate["tree_id"] for candidate in payload["top_candidates"][:2]] == [
        "orders",
        "revenue",
    ]


def test_trees_investigate_bundles_deterministic_steps(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    evaluate_calls: list[tuple[str, str, str, str, str]] = []
    root_cause_calls: list[dict[str, object]] = []

    def mock_validate_tree(self, tree_id):
        assert tree_id == "revenue"
        return {
            "tree_id": "revenue",
            "tree_label": "Revenue",
            "valid": True,
            "dimensions_declared": ["channel", "country"],
            "supported_dimensions": ["channel", "country"],
            "leaf_nodes": [],
            "errors": [],
            "warnings": [],
        }

    def mock_evaluate_tree(self, tree_id, current_from, current_to, comparison_from, comparison_to):
        evaluate_calls.append((tree_id, current_from, current_to, comparison_from, comparison_to))
        return {
            "tree_id": tree_id,
            "tree_label": tree_id.title(),
            "root_node_id": tree_id,
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 100,
            "comparison_value": 90,
            "delta_value": 10,
            "delta_ratio": 0.1111111111,
            "top_contributors": [],
            "nodes": [
                {
                    "id": tree_id,
                    "label": tree_id.title(),
                    "kind": "formula",
                    "current_value": 100,
                    "comparison_value": 90,
                    "delta_value": 10,
                    "delta_ratio": 0.1111111111,
                    "contributions": [],
                }
            ],
            "warnings": [],
        }

    def mock_root_cause_tree(
        self,
        tree_id,
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        *,
        segment_by,
        filters,
        max_depth,
        max_branching,
        max_segments,
        min_contribution_share,
    ):
        root_cause_calls.append(
            {
                "tree_id": tree_id,
                "segment_by": list(segment_by),
                "filters": filters,
                "max_depth": max_depth,
                "max_branching": max_branching,
                "max_segments": max_segments,
                "min_contribution_share": min_contribution_share,
            }
        )
        return {
            "tree_id": tree_id,
            "tree_label": tree_id.title(),
            "root_node_id": tree_id,
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 100,
            "comparison_value": 90,
            "delta_value": 10,
            "delta_ratio": 0.1111111111,
            "dimensions_considered": list(segment_by),
            "time_slice_grain": "day",
            "time_slices": [],
            "mix_shift": None,
            "conclusion": None,
            "findings": [],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.validate_tree", mock_validate_tree)
    monkeypatch.setattr("qluent_cli.trees.QluentClient.evaluate_tree", mock_evaluate_tree)
    monkeypatch.setattr("qluent_cli.trees.QluentClient.root_cause_tree", mock_root_cause_tree)

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
            "--trend-as-of",
            "2026-03-17",
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
    assert payload["validation"]["supported_dimensions"] == ["channel", "country"]
    assert payload["segment_by_used"] == ["channel", "country"]
    assert len(payload["trend"]["evaluations"]) == 2
    assert payload["evaluation"]["tree_id"] == "revenue"
    assert payload["root_cause"]["dimensions_considered"] == ["channel", "country"]
    assert [item["tree_id"] for item in payload["comparison"]["results"]] == ["orders"]
    assert payload["filters"] == {"country": ["SE"]}
    assert payload["step_errors"] == {}
    assert payload["agent"]["status"] == "partially_resolved"
    assert "ranked deterministic conclusion" in payload["agent"]["gaps"][0]
    assert [item["kind"] for item in payload["agent"]["recommended_next_steps"]] == [
        "comparison",
        "comparison",
        "comparison",
    ]
    assert len(evaluate_calls) == 4
    assert root_cause_calls[0]["segment_by"] == ["channel", "country"]


def test_trees_investigate_matches_question_for_agent_flow(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    evaluate_calls: list[tuple[str, str, str, str, str]] = []

    def mock_list_trees(self):
        return {
            "trees": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "description": "Total revenue from completed orders",
                    "dimensions": ["channel", "country"],
                    "nodes": [
                        {"id": "revenue", "label": "Revenue", "kind": "formula"},
                        {"id": "orders", "label": "Orders", "kind": "sql_metric"},
                    ],
                }
            ]
        }

    def mock_validate_tree(self, tree_id):
        assert tree_id == "revenue"
        return {
            "tree_id": "revenue",
            "tree_label": "Revenue",
            "valid": True,
            "dimensions_declared": ["channel", "country"],
            "supported_dimensions": ["channel", "country"],
            "leaf_nodes": [],
            "errors": [],
            "warnings": [],
        }

    def mock_evaluate_tree(self, tree_id, current_from, current_to, comparison_from, comparison_to):
        evaluate_calls.append((tree_id, current_from, current_to, comparison_from, comparison_to))
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "root_node_id": tree_id,
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 900,
            "comparison_value": 1000,
            "delta_value": -100,
            "delta_ratio": -0.1,
            "top_contributors": [
                {
                    "node_id": "orders",
                    "label": "Orders",
                    "delta_value": -100,
                    "delta_share": 1.0,
                }
            ],
            "nodes": [],
            "warnings": [],
        }

    def mock_root_cause_tree(
        self,
        tree_id,
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        *,
        segment_by,
        filters,
        max_depth,
        max_branching,
        max_segments,
        min_contribution_share,
    ):
        assert tree_id == "revenue"
        assert current_from == "2026-03-09"
        assert current_to == "2026-03-15"
        assert comparison_from == "2026-03-02"
        assert comparison_to == "2026-03-08"
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "root_node_id": tree_id,
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
            "current_value": 900,
            "comparison_value": 1000,
            "delta_value": -100,
            "delta_ratio": -0.1,
            "dimensions_considered": ["channel", "country"],
            "time_slice_grain": "day",
            "time_slices": [],
            "mix_shift": None,
            "conclusion": {
                "confidence": "high",
                "confidence_score": 0.85,
                "confidence_type": "evidence_coverage_heuristic",
                "confidence_description": "Broad deterministic evidence is present.",
                "evidence_types_present": ["driver", "segment"],
                "evidence_types_missing": [],
                "confidence_factors": [],
                "takeaways": [
                    {
                        "kind": "driver",
                        "title": "Orders drove the decline",
                        "summary": "Orders explain most of the revenue decline.",
                        "score": 1.2,
                        "node_id": "orders",
                        "path": ["revenue", "orders"],
                        "delta_value": -100,
                        "effect_value": None,
                        "share_of_change": 1.0,
                        "dimension": None,
                        "segment": None,
                        "current_window": None,
                        "comparison_window": None,
                    }
                ],
                "unresolved_nodes": [],
            },
            "findings": [],
            "warnings": [],
        }

    monkeypatch.setattr("qluent_cli.trees.QluentClient.list_trees", mock_list_trees)
    monkeypatch.setattr("qluent_cli.trees.QluentClient.validate_tree", mock_validate_tree)
    monkeypatch.setattr("qluent_cli.trees.QluentClient.evaluate_tree", mock_evaluate_tree)
    monkeypatch.setattr("qluent_cli.trees.QluentClient.root_cause_tree", mock_root_cause_tree)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "investigate",
            "--question",
            "Why did revenue drop from 2026-03-09 to 2026-03-15 compared with 2026-03-02 to 2026-03-08?",
            "--json-output",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["question"].startswith("Why did revenue drop")
    assert payload["match"]["matched"] is True
    assert payload["tree_id"] == "revenue"
    assert payload["period_label"] == "Mar 9–Mar 15 vs Mar 2–Mar 8"
    assert payload["agent"]["status"] == "resolved"
    assert payload["agent"]["top_findings"] == [
        "Orders explain most of the revenue decline."
    ]
    assert payload["agent"]["recommended_next_steps"][0]["kind"] == "comparison"
    assert (
        "revenue",
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    ) in evaluate_calls
