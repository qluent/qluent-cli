"""Project-specific suggestion command."""

from __future__ import annotations

import json
from typing import Any

import click
import httpx

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config


def _node_label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("id") or "metric")


def _node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or node.get("node_id") or "")


def _tree_dimensions(tree: dict[str, Any]) -> list[str]:
    candidates = (
        tree.get("dimensions")
        or tree.get("supported_dimensions")
        or tree.get("dimensions_declared")
        or []
    )
    return [str(item) for item in candidates if item]


def _metric_nodes(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        node
        for node in tree.get("nodes", [])
        if node.get("kind") == "sql_metric" and (_node_id(node) or _node_label(node))
    ]


def _root_node(tree: dict[str, Any]) -> dict[str, Any] | None:
    root_id = tree.get("root_node_id")
    if root_id:
        for node in tree.get("nodes", []):
            if node.get("id") == root_id or node.get("node_id") == root_id:
                return node
    return (tree.get("nodes") or [None])[0]


def _catalog_dimensions(catalog: dict[str, Any]) -> list[str]:
    derived = [str(item) for item in catalog.get("derived_dimensions") or [] if item]
    columns: list[str] = []
    for base in (catalog.get("bases") or {}).values():
        raw_columns = base.get("columns") if isinstance(base, dict) else []
        if isinstance(raw_columns, dict):
            raw_columns = raw_columns.keys()
        for column in raw_columns or []:
            name = str(column)
            if name and name not in columns:
                columns.append(name)
    return derived + [name for name in columns if name not in derived]


def build_query_suggestions(catalog_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build query-first examples from the project's closed-world catalog."""
    if not catalog_data or catalog_data.get("success") is False:
        return []
    catalog = catalog_data.get("catalog") or {}
    metrics = [str(name) for name in (catalog.get("metrics") or {}) if name]
    bases = [str(name) for name in (catalog.get("bases") or {}) if name]
    dimensions = _catalog_dimensions(catalog)
    subjects = metrics or bases
    suggestions: list[dict[str, Any]] = []

    for subject in subjects[:3]:
        dimension = next(
            (name for name in dimensions if name != subject),
            None,
        )
        if dimension:
            question = f"Show {subject} by {dimension} for the last complete month."
        else:
            question = f"What was {subject} for the last complete month?"
        suggestions.append(
            {
                "tree_id": None,
                "tree_label": "Catalog queries",
                "analysis_type": "query",
                "example_question": question,
                "recommended_command": f'qluent query "{question}" --json-output',
                "preferred_engine": "composed_plan",
                "rationale": (
                    "Starts from catalog vocabulary; agents should use a deterministic "
                    "composed plan when coverage is complete and fall back to the NL query."
                ),
            }
        )
    return suggestions


def build_suggestions(
    trees_data: dict[str, Any],
    catalog_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build query-first examples, followed by advanced metric-tree analyses."""
    trees = trees_data.get("trees") or []
    suggestions = build_query_suggestions(catalog_data)

    for index, tree in enumerate(trees):
        tree_id = str(tree.get("id") or "")
        if not tree_id:
            continue
        tree_label = str(tree.get("label") or tree_id)
        root = _root_node(tree) or {}
        root_label = _node_label(root) if root else tree_label
        root_id = _node_id(root) or tree_id
        metrics = _metric_nodes(tree)
        dimensions = _tree_dimensions(tree)

        suggestions.append(
            {
                "tree_id": tree_id,
                "tree_label": tree_label,
                "analysis_type": "rca",
                "example_question": f"Why did {root_label} change last complete month?",
                "recommended_command": (
                    f'qluent trees investigate {tree_id} --period "last month" --json-output'
                ),
                "rationale": "Uses the tree RCA bundle for root-cause, trend, segment, and lever evidence.",
            }
        )
        suggestions.append(
            {
                "tree_id": tree_id,
                "tree_label": tree_label,
                "analysis_type": "trend",
                "example_question": f"Is {root_label} trending consistently over recent weeks?",
                "recommended_command": (
                    f"qluent trees trend {tree_id} --periods 4 --grain week --json-output"
                ),
                "rationale": "The tree supports multi-period evaluation through its root metric.",
            }
        )

        if dimensions:
            dimension = dimensions[0]
            suggestions.append(
                {
                    "tree_id": tree_id,
                    "tree_label": tree_label,
                    "analysis_type": "segmentation",
                    "example_question": (
                        f"Which {dimension} segment concentrated the {root_label} movement?"
                    ),
                    "recommended_command": (
                        f'qluent trees investigate {tree_id} --period "last month" '
                        f"--segment-by {dimension} --json-output"
                    ),
                    "rationale": (
                        f"Tree metadata exposes the `{dimension}` dimension for segment RCA."
                    ),
                }
            )

        if len(metrics) >= 2:
            lever = metrics[0]
            if _node_id(lever) == root_id and len(metrics) > 1:
                lever = metrics[1]
            suggestions.append(
                {
                    "tree_id": tree_id,
                    "tree_label": tree_label,
                    "analysis_type": "elasticity",
                    "example_question": (
                        f"Which lever should we inspect to move {root_label}?"
                    ),
                    "recommended_command": (
                        f'qluent trees levers {tree_id} --period "last month" --json-output'
                    ),
                    "rationale": (
                        f"Tree includes metric nodes such as `{_node_id(lever) or _node_label(lever)}` "
                        "that can be ranked as levers when evaluation returns elasticities."
                    ),
                }
            )

        compare_target = next(
            (
                str(other.get("id"))
                for offset, other in enumerate(trees)
                if offset != index and other.get("id")
            ),
            None,
        )
        if compare_target:
            suggestions.append(
                {
                    "tree_id": tree_id,
                    "tree_label": tree_label,
                    "analysis_type": "compare",
                    "example_question": (
                        f"Does {tree_label} move with {compare_target} over the same period?"
                    ),
                    "recommended_command": (
                        f'qluent trees compare {tree_id} {compare_target} --period "last month" '
                        "--json-output"
                    ),
                    "rationale": "Compare only uses tree ids advertised by the connected project.",
                }
            )

    return suggestions


def format_suggestions(suggestions: list[dict[str, Any]]) -> str:
    if not suggestions:
        return "No project-specific suggestions available."

    lines: list[str] = []
    current_tree: str | None = None
    for suggestion in suggestions:
        tree_label = str(suggestion["tree_label"])
        if tree_label != current_tree:
            if lines:
                lines.append("")
            lines.append(tree_label)
            current_tree = tree_label
        lines.append(f"- {suggestion['example_question']}")
    return "\n".join(lines)


@click.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def suggestions(as_json: bool) -> None:
    """Show query-first examples and advanced tree analyses for the project."""
    config = load_config()
    client = QluentClient(config)
    try:
        catalog_data = client.get_query_catalog()
    except httpx.HTTPStatusError:
        catalog_data = None
    data = {
        "default_workflow": "query",
        "suggestions": build_suggestions(client.list_trees(), catalog_data),
    }

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_suggestions(data["suggestions"]))
