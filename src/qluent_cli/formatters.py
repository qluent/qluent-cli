"""Human-readable output formatting for metric tree results."""

from __future__ import annotations

from typing import Any


def _fmt_num(value: float, signed: bool = False) -> str:
    """Format a number with commas and optional sign."""
    if abs(value) >= 1:
        formatted = f"{abs(value):,.0f}"
    else:
        formatted = f"{abs(value):,.2f}"
    if signed:
        prefix = "+" if value >= 0 else "-"
        return f"{prefix}${formatted}"
    return f"${formatted}"


def _fmt_pct(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio * 100:+.1f}%"


def _fmt_share(share: float | None) -> str:
    if share is None:
        return "n/a"
    return f"{share * 100:.0f}%"


def _fmt_date(d: str) -> str:
    """Format ISO date as short form: Mar 10."""
    from datetime import date as dt_date

    d_obj = dt_date.fromisoformat(d)
    return d_obj.strftime("%b %-d")


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
    lines.append("")

    def walk(node_id: str, indent: int, prefix: str) -> None:
        node = nodes_by_id.get(node_id)
        if not node:
            return
        kind_tag = "sql" if node["kind"] == "sql_metric" else node.get("formula", "")
        lines.append(f"{prefix}{node['label']} [{kind_tag}]")
        children = node.get("children", [])
        for i, child_id in enumerate(children):
            is_last = i == len(children) - 1
            child_prefix = indent * " " + ("└── " if is_last else "├── ")
            walk(child_id, indent + 4, child_prefix)

    walk(root_id, 0, "  ")
    return "\n".join(lines)


def format_evaluation(data: dict[str, Any]) -> str:
    """Format evaluation results as a readable summary."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    header = (
        f"{data['tree_label']} — "
        f"{_fmt_date(cw['date_from'])}–{_fmt_date(cw['date_to'])} vs "
        f"{_fmt_date(pw['date_from'])}–{_fmt_date(pw['date_to'])}"
    )

    current = data["current_value"]
    comparison = data["comparison_value"]
    delta = data["delta_value"]
    ratio = data.get("delta_ratio")

    summary = (
        f"  {data['tree_label']}: {_fmt_num(comparison)} → {_fmt_num(current)}  "
        f"Δ {_fmt_num(delta, signed=True)} ({_fmt_pct(ratio)})"
    )

    lines = [header, "", summary, ""]

    # Top contributors
    contributors = data.get("top_contributors", [])
    if contributors:
        lines.append("  Top contributors:")
        max_label = max(len(c["label"]) for c in contributors) if contributors else 0
        for c in contributors:
            label = c["label"].ljust(max_label)
            lines.append(
                f"    {label}  {_fmt_num(c['delta_value'], signed=True):>12}  "
                f"({_fmt_share(c.get('delta_share'))} of change)"
            )
        lines.append("")

    # Full node breakdown
    nodes = data.get("nodes", [])
    if nodes:
        lines.append("  All nodes:")
        max_label = max(len(n["label"]) for n in nodes) if nodes else 0
        for n in nodes:
            label = n["label"].ljust(max_label)
            lines.append(
                f"    {label}  "
                f"{_fmt_num(n['comparison_value']):>12} → {_fmt_num(n['current_value']):>12}  "
                f"Δ {_fmt_num(n['delta_value'], signed=True):>12}  {_fmt_pct(n.get('delta_ratio')):>7}"
            )

    # Warnings
    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"  ⚠ {w}")

    return "\n".join(lines)
