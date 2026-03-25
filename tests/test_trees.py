from __future__ import annotations

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
