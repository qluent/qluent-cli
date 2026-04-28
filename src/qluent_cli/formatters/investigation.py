"""Formatter for the bundled investigation result.

Investigation aggregates output from validation, trend, evaluation, levers,
RCA, and comparison — so this module pulls the result-kind formatters
from their dedicated submodules.
"""

from __future__ import annotations

from typing import Any

from qluent_cli.formatters.comparison import format_comparison
from qluent_cli.formatters.evaluation import format_evaluation, format_levers
from qluent_cli.formatters.rca import format_root_cause
from qluent_cli.formatters.trend import format_trend
from qluent_cli.formatters.validation import format_tree_validation


def _fmt_header(data: dict[str, Any], lines: list[str]) -> str:
    """Append investigation header lines and return the resolved tree label."""
    evaluation = data.get("evaluation") or {}
    validation = data.get("validation") or {}
    root_cause = data.get("root_cause") or {}
    agent = data.get("agent") or {}
    tree_label = (
        evaluation.get("tree_label")
        or validation.get("tree_label")
        or root_cause.get("tree_label")
        or data.get("tree_label")
        or data.get("tree_id", "?")
    )

    lines.extend([f"{tree_label} Investigation", ""])
    if data.get("period_label"):
        lines.append(f"  Period: {data['period_label']}")
    if data.get("segment_by_used"):
        lines.append("  Segment cuts: " + ", ".join(data["segment_by_used"]))
    if data.get("filters"):
        rendered_filters = []
        for key, values in sorted(data["filters"].items()):
            rendered_filters.append(f"{key}={','.join(values)}")
        if rendered_filters:
            lines.append("  Filters: " + "; ".join(rendered_filters))
    if agent.get("status"):
        lines.append(
            "  Investigation status: "
            + str(agent["status"]).replace("_", " ")
        )

    return tree_label


def _fmt_agent(data: dict[str, Any], lines: list[str]) -> None:
    agent = data.get("agent") or {}

    top_findings = agent.get("top_findings") or []
    if top_findings:
        lines.extend(["", "  Top findings:"])
        for index, finding in enumerate(top_findings[:3], start=1):
            lines.append(f"    {index}. {finding}")

    gaps = agent.get("gaps") or []
    if gaps:
        lines.extend(["", "  Evidence gaps:"])
        for gap in gaps[:6]:
            lines.append(f"    - {gap}")

    recommended_next_steps = agent.get("recommended_next_steps") or []
    if recommended_next_steps:
        lines.extend(["", "  Recommended next steps:"])
        for step in recommended_next_steps[:4]:
            title = step.get("title") or step.get("kind") or "Next step"
            lines.append(f"    - {title}: {step.get('why', '')}".rstrip())
            if step.get("command"):
                lines.append(f"      {step['command']}")


def _fmt_step_results(
    data: dict[str, Any], tree_label: str, lines: list[str]
) -> None:
    step_errors = data.get("step_errors") or {}
    validation = data.get("validation") or {}
    evaluation = data.get("evaluation") or {}
    levers = data.get("levers") or {}
    root_cause = data.get("root_cause") or {}

    if validation:
        lines.extend(["", format_tree_validation(validation)])
    elif "validation" in step_errors:
        lines.extend(["", f"Validation failed: {step_errors['validation']}"])

    trend = data.get("trend") or {}
    trend_evaluations = trend.get("evaluations") or []
    if trend_evaluations:
        lines.extend(
            [
                "",
                format_trend(
                    trend_evaluations[0].get("tree_label", tree_label),
                    trend_evaluations,
                    trend.get("grain", "week"),
                ),
            ]
        )
    elif "trend" in step_errors:
        lines.extend(["", f"Trend failed: {step_errors['trend']}"])

    if evaluation:
        lines.extend(["", format_evaluation(evaluation)])
    elif "evaluation" in step_errors:
        lines.extend(["", f"Evaluation failed: {step_errors['evaluation']}"])

    if levers.get("top_levers"):
        lines.extend(["", format_levers(levers)])

    if root_cause:
        lines.extend(["", format_root_cause(root_cause)])
    elif "root_cause" in step_errors:
        lines.extend(["", f"Root cause failed: {step_errors['root_cause']}"])

    comparison = data.get("comparison") or {}
    comparison_results = comparison.get("results") or []
    if comparison_results:
        tree_results = [
            (result.get("tree_label", result.get("tree_id", "?")), result)
            for result in comparison_results
        ]
        lines.extend(
            [
                "",
                format_comparison(tree_results, comparison.get("period_label", data.get("period_label", ""))),
            ]
        )
    comparison_errors = comparison.get("errors") or {}
    if comparison_errors:
        lines.append("")
        lines.append("Comparison errors:")
        for tree_id, message in sorted(comparison_errors.items()):
            lines.append(f"  ! {tree_id}: {message}")

    residual_errors = {
        key: value
        for key, value in step_errors.items()
        if key not in {"validation", "trend", "evaluation", "root_cause"}
    }
    if residual_errors:
        lines.append("")
        lines.append("Other step errors:")
        for key, message in sorted(residual_errors.items()):
            lines.append(f"  ! {key}: {message}")


def format_investigation(data: dict[str, Any]) -> str:
    """Format a bundled metric tree investigation."""
    lines: list[str] = []
    tree_label = _fmt_header(data, lines)
    _fmt_agent(data, lines)
    _fmt_step_results(data, tree_label, lines)
    return "\n".join(lines)
