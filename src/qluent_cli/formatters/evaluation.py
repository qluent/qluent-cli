"""Formatters for tree evaluation and lever-analysis results."""

from __future__ import annotations

from typing import Any

from qluent_cli.formatters._common import (
    fmt_date,
    fmt_direction,
    fmt_elasticity,
    fmt_num,
    fmt_pct,
    fmt_share,
)


def format_evaluation(data: dict[str, Any]) -> str:
    """Format evaluation results as a readable summary."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    header = (
        f"{data['tree_label']} — "
        f"{fmt_date(cw['date_from'])}–{fmt_date(cw['date_to'])} vs "
        f"{fmt_date(pw['date_from'])}–{fmt_date(pw['date_to'])}"
    )

    current = data["current_value"]
    comparison = data["comparison_value"]
    delta = data["delta_value"]
    ratio = data.get("delta_ratio")

    summary = (
        f"  {data['tree_label']}: {fmt_num(comparison)} → {fmt_num(current)}  "
        f"Δ {fmt_num(delta, signed=True)} ({fmt_pct(ratio)})"
    )

    lines = [header, "", summary, ""]

    contributors = data.get("top_contributors", [])
    if contributors:
        lines.append("  Top contributors:")
        max_label = max(len(c["label"]) for c in contributors) if contributors else 0
        for c in contributors:
            label = c["label"].ljust(max_label)
            lines.append(
                f"    {label}  {fmt_num(c['delta_value'], signed=True):>12}  "
                f"({fmt_share(c.get('delta_share'))} of change)"
            )
        lines.append("")

    nodes = data.get("nodes", [])
    if nodes:
        has_elasticity = any(n.get("elasticity") is not None for n in nodes)
        lines.append("  All nodes:")
        max_label = max(len(n["label"]) for n in nodes) if nodes else 0
        for n in nodes:
            label = n["label"].ljust(max_label)
            line = (
                f"    {label}  "
                f"{fmt_num(n['comparison_value']):>12} → {fmt_num(n['current_value']):>12}  "
                f"Δ {fmt_num(n['delta_value'], signed=True):>12}  {fmt_pct(n.get('delta_ratio')):>7}"
            )
            if has_elasticity:
                line += f"  ε {fmt_elasticity(n.get('elasticity')):>6}"
            lines.append(line)

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        for w in warnings:
            lines.append(f"  ! {w}")

    return "\n".join(lines)


def format_levers(data: dict[str, Any]) -> str:
    """Format lever-analysis results from evaluation elasticities."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    header = (
        f"{data['tree_label']} Levers — "
        f"{fmt_date(cw['date_from'])}–{fmt_date(cw['date_to'])} vs "
        f"{fmt_date(pw['date_from'])}–{fmt_date(pw['date_to'])}"
    )

    lines = [
        header,
        "",
        (
            f"  {data['tree_label']}: {fmt_num(data['comparison_value'])} → {fmt_num(data['current_value'])}  "
            f"Δ {fmt_num(data['delta_value'], signed=True)} ({fmt_pct(data.get('delta_ratio'))})"
        ),
    ]

    top_levers = data.get("top_levers") or []
    if top_levers:
        lines.extend(["", "  Top levers:"])
        for lever in top_levers:
            lines.append(
                f"    {lever['label']}  ε {fmt_elasticity(lever.get('elasticity')):>6}  "
                f"best action: {fmt_direction(lever.get('recommended_direction'))}"
            )
            for impact in lever.get("scenario_impacts") or []:
                lines.append(
                    f"      +{impact['node_change_ratio'] * 100:.0f}% node → "
                    f"root {fmt_pct(impact.get('estimated_root_delta_ratio'))} "
                    f"(Δ {fmt_num(impact['estimated_root_delta_value'], signed=True)})"
                )
    else:
        lines.extend(["", "  No non-root nodes had defined elasticities."])

    warnings = data.get("warnings") or []
    if warnings:
        lines.append("")
        for warning in warnings:
            lines.append(f"  ! {warning}")

    return "\n".join(lines)
