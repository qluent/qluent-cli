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
