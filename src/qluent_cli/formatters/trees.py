"""Formatters for tree listing and tree detail views."""

from __future__ import annotations

from typing import Any


def format_tree_list(data: dict[str, Any]) -> str:
    """Format the list of metric trees."""
    trees = data.get("trees", [])
    if not trees:
        return "No metric trees configured."

    lines = []
    for tree in trees:
        nodes = tree.get("nodes", [])
        sql_count = sum(1 for n in nodes if n.get("kind") == "sql_metric")
        formula_count = len(nodes) - sql_count
        lines.append(f"  {tree['id']}")
        lines.append(f"    {tree['label']}")
        if tree.get("description"):
            lines.append(f"    {tree['description']}")
        lines.append(f"    {len(nodes)} nodes ({formula_count} formula, {sql_count} sql)")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_tree_detail(data: dict[str, Any]) -> str:
    """Format a single tree as an indented hierarchy."""
    nodes_by_id = {n["id"]: n for n in data.get("nodes", [])}
    root_id = data.get("root_node_id", "")

    lines = [f"{data.get('label', data.get('id', '?'))}"]
    if data.get("description"):
        lines.append(f"  {data['description']}")
    if data.get("redacted"):
        lines.append(
            f"  {data.get('redaction_reason') or 'Client-safe mode redacted sensitive tree fields.'}"
        )
    lines.append("")

    def walk(node_id: str, indent: int, prefix: str) -> None:
        node = nodes_by_id.get(node_id)
        if not node:
            return
        if node["kind"] == "sql_metric":
            kind_tag = "sql"
        else:
            kind_tag = "formula" if data.get("redacted") else node.get("formula", "formula")
        lines.append(f"{prefix}{node['label']} [{kind_tag}]")
        children = node.get("children", [])
        for i, child_id in enumerate(children):
            is_last = i == len(children) - 1
            child_prefix = indent * " " + ("└── " if is_last else "├── ")
            walk(child_id, indent + 4, child_prefix)

    walk(root_id, 0, "  ")
    return "\n".join(lines)
