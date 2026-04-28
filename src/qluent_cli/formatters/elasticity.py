"""Formatter for elasticity analysis results."""

from __future__ import annotations

from typing import Any

from qluent_cli.formatters._common import fmt_date, fmt_elasticity


def format_elasticity(data: dict[str, Any]) -> str:
    """Format elasticity analysis results."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    title = data.get("tree_label") or data.get("tree_id", "Elasticity")
    evidence_type = str(data.get("evidence_type") or "observed_correlation").replace("_", " ")
    confidence = data.get("confidence") or "unknown"
    lines = [
        (
            f"{title} Elasticity — "
            f"{fmt_date(cw['date_from'])}–{fmt_date(cw['date_to'])} vs "
            f"{fmt_date(pw['date_from'])}–{fmt_date(pw['date_to'])}"
        ),
        "",
        f"  Evidence: {evidence_type} | confidence: {confidence}",
        f"  Outcome: {data.get('outcome')} | lever: {data.get('lever')}",
    ]
    if data.get("dimension"):
        lines.append(f"  Dimension: {data['dimension']}")

    results = data.get("results") or []
    if results:
        lines.extend(["", "  Results:"])
        for result in results[:10]:
            label = result.get("segment") or result.get("label") or "overall"
            line = (
                f"    {label}: ε {fmt_elasticity(result.get('elasticity'))} "
                f"| confidence {result.get('confidence', confidence)}"
            )
            if result.get("low_confidence"):
                line += " | low confidence"
            lines.append(line)

    warnings = data.get("warnings") or []
    if warnings:
        lines.append("")
        for warning in warnings:
            lines.append(f"  ! {warning}")

    return "\n".join(lines)
