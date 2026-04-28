"""Formatter for multi-period trend results."""

from __future__ import annotations

from qluent_cli.formatters._common import fmt_date, fmt_pct


def _classify_trend(ratios: list[float | None]) -> str:
    """Classify a series of delta ratios into a trend label."""
    valid = [r for r in ratios if r is not None]
    if not valid:
        return ""
    if all(abs(r) <= 0.02 for r in valid):
        return "stable"
    if len(valid) < 2:
        return ""

    signs = [1 if r > 0 else (-1 if r < 0 else 0) for r in valid]
    changes = sum(
        1
        for i in range(1, len(signs))
        if signs[i] != signs[i - 1] and signs[i] != 0 and signs[i - 1] != 0
    )

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

    if grain == "week":
        labels = [f"W-{n - 1 - i}" if i < n - 1 else "W0" for i in range(n)]
    else:
        labels = [fmt_date(e["current_window"]["date_from"]) for e in evaluations]

    node_order = [node["id"] for node in evaluations[0].get("nodes", [])]
    node_labels = {
        node["id"]: node["label"]
        for node in evaluations[0].get("nodes", [])
    }

    ratio_matrix: dict[str, list[float | None]] = {}
    for node_id in node_order:
        ratio_matrix[node_id] = []
        for ev in evaluations:
            node = next((nd for nd in ev.get("nodes", []) if nd["id"] == node_id), None)
            ratio_matrix[node_id].append(node.get("delta_ratio") if node else None)

    lines = [f"{tree_label} — {grain_label} Trend (last {n} periods)", ""]

    col_width = max(len(la) for la in labels) + 2
    col_width = max(col_width, 9)
    max_label_len = max(len(node_labels.get(nid, nid)) for nid in node_order) if node_order else 0
    header_line = " " * (max_label_len + 4) + "".join(la.rjust(col_width) for la in labels) + "   Trend"
    lines.append(header_line)

    for node_id in node_order:
        label = node_labels.get(node_id, node_id).ljust(max_label_len)
        ratios = ratio_matrix[node_id]
        cells = "".join(fmt_pct(r).rjust(col_width) for r in ratios)
        trend = _classify_trend(ratios)
        lines.append(f"    {label}{cells}   {trend}")

    return "\n".join(lines)
