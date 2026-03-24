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


def _classify_trend(ratios: list[float | None]) -> str:
    """Classify a series of delta ratios into a trend label."""
    valid = [r for r in ratios if r is not None]
    if not valid:
        return ""
    if all(abs(r) <= 0.02 for r in valid):
        return "stable"
    if len(valid) < 2:
        return ""

    # Count direction changes
    signs = [1 if r > 0 else (-1 if r < 0 else 0) for r in valid]
    changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1] and signs[i] != 0 and signs[i - 1] != 0)

    if changes >= 2:
        return "volatile"

    last, prev = valid[-1], valid[-2]
    if prev < 0 and last > 0:
        return "recovering"
    if prev > 0 and last < 0:
        return "declining"
    if last > 0 and prev > 0:
        return "accelerating" if last > prev else "decelerating"
    if last < 0 and prev < 0:
        return "worsening" if last < prev else "improving"
    return ""


def format_trend(tree_label: str, evaluations: list[dict], grain: str) -> str:
    """Format multi-period trend results."""
    if not evaluations:
        return "No data."

    grain_label = "Weekly" if grain == "week" else "Monthly"
    n = len(evaluations)

    # Build period labels
    if grain == "week":
        labels = [f"W-{n - 1 - i}" if i < n - 1 else "W0" for i in range(n)]
    else:
        labels = [_fmt_date(e["current_window"]["date_from"]) for e in evaluations]

    # Collect all node IDs in order from first evaluation
    node_order = [node["id"] for node in evaluations[0].get("nodes", [])]
    node_labels = {
        node["id"]: node["label"]
        for node in evaluations[0].get("nodes", [])
    }

    # Build ratio matrix: node_id -> [ratio_per_period]
    ratio_matrix: dict[str, list[float | None]] = {}
    for node_id in node_order:
        ratio_matrix[node_id] = []
        for ev in evaluations:
            node = next((nd for nd in ev.get("nodes", []) if nd["id"] == node_id), None)
            ratio_matrix[node_id].append(node.get("delta_ratio") if node else None)

    # Format
    lines = [f"{tree_label} — {grain_label} Trend (last {n} periods)", ""]

    col_width = max(len(la) for la in labels) + 2
    col_width = max(col_width, 9)  # min width for percentage values
    max_label_len = max(len(node_labels.get(nid, nid)) for nid in node_order) if node_order else 0
    header_line = " " * (max_label_len + 4) + "".join(la.rjust(col_width) for la in labels) + "   Trend"
    lines.append(header_line)

    for node_id in node_order:
        label = node_labels.get(node_id, node_id).ljust(max_label_len)
        ratios = ratio_matrix[node_id]
        cells = "".join(_fmt_pct(r).rjust(col_width) for r in ratios)
        trend = _classify_trend(ratios)
        lines.append(f"    {label}{cells}   {trend}")

    return "\n".join(lines)


def format_comparison(tree_results: list[tuple[str, dict]], period_label: str) -> str:
    """Format side-by-side comparison of multiple trees for the same period.

    Matches nodes by position in the tree (index), not by ID, since trees with
    the same channel structure (e.g., Revenue vs Order Volume) use different IDs
    but share the same hierarchical shape.
    """
    if not tree_results:
        return "No data."

    tree_labels = [label for label, _ in tree_results]
    header = " vs ".join(tree_labels) + f" — {period_label}"

    # Use the tree with the most nodes as the row basis
    max_nodes = 0
    base_idx = 0
    for i, (_, data) in enumerate(tree_results):
        n = len(data.get("nodes", []))
        if n > max_nodes:
            max_nodes = n
            base_idx = i

    _, base_data = tree_results[base_idx]
    base_nodes = base_data.get("nodes", [])
    row_labels = [nd["label"] for nd in base_nodes]

    # Build ratio list per tree by position index
    tree_ratio_lists: list[list[float | None]] = []
    for _, data in tree_results:
        nodes = data.get("nodes", [])
        tree_ratio_lists.append([
            nodes[i].get("delta_ratio") if i < len(nodes) else None
            for i in range(max_nodes)
        ])

    # Format
    max_label_len = max(len(la) for la in row_labels) if row_labels else 0
    col_width = max(len(la) for la in tree_labels) + 2
    col_width = max(col_width, 9)

    lines = [header, ""]
    col_header = " " * (max_label_len + 4) + "".join(la.rjust(col_width) for la in tree_labels)
    lines.append(col_header)

    for i, label in enumerate(row_labels):
        padded = label.ljust(max_label_len)
        cells = ""
        for ratios in tree_ratio_lists:
            r = ratios[i] if i < len(ratios) else None
            cells += _fmt_pct(r).rjust(col_width) if r is not None else "—".rjust(col_width)
        lines.append(f"    {padded}{cells}")

    return "\n".join(lines)
