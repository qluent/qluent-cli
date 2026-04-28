from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli
from qluent_cli.suggestions import build_suggestions


TREE_DATA = {
    "trees": [
        {
            "id": "revenue",
            "label": "Revenue",
            "root_node_id": "net_revenue",
            "dimensions": ["region", "channel"],
            "nodes": [
                {"id": "net_revenue", "label": "Net Revenue", "kind": "formula"},
                {"id": "orders", "label": "Orders", "kind": "sql_metric"},
                {"id": "aov", "label": "AOV", "kind": "sql_metric"},
            ],
        },
        {
            "id": "growth",
            "label": "Growth",
            "root_node_id": "active_users",
            "nodes": [
                {"id": "active_users", "label": "Active Users", "kind": "sql_metric"},
                {"id": "frequency", "label": "Orders/User", "kind": "sql_metric"},
            ],
        },
    ]
}


def test_build_suggestions_derives_examples_from_tree_metadata():
    suggestions = build_suggestions(TREE_DATA)

    assert {item["analysis_type"] for item in suggestions} >= {
        "rca",
        "segmentation",
        "trend",
        "elasticity",
        "compare",
    }
    revenue_suggestions = [item for item in suggestions if item["tree_id"] == "revenue"]
    assert any("Net Revenue" in item["example_question"] for item in revenue_suggestions)
    assert any("--segment-by region" in item["recommended_command"] for item in revenue_suggestions)
    assert any(
        item["recommended_command"]
        == 'qluent trees compare revenue growth --period "last month" --json-output'
        for item in revenue_suggestions
    )


def test_suggestions_json_output_contains_agent_fields(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.suggestions.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )
    monkeypatch.setattr("qluent_cli.suggestions.QluentClient.list_trees", lambda self: TREE_DATA)

    result = CliRunner().invoke(cli, ["suggestions", "--json-output"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    first = payload["suggestions"][0]
    assert {
        "tree_id",
        "tree_label",
        "example_question",
        "recommended_command",
        "rationale",
    } <= set(first)
    assert first["tree_id"] == "revenue"


def test_suggestions_human_output_groups_by_tree(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.suggestions.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )
    monkeypatch.setattr("qluent_cli.suggestions.QluentClient.list_trees", lambda self: TREE_DATA)

    result = CliRunner().invoke(cli, ["suggestions"])

    assert result.exit_code == 0
    assert "Revenue\n- Why did Net Revenue change last complete month?" in result.output
    assert "Growth\n- Why did Active Users change last complete month?" in result.output
