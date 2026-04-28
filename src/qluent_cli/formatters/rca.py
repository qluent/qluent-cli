"""Formatter for root-cause analysis results."""

from __future__ import annotations

from typing import Any

from qluent_cli.rca_contracts import RCAOutput
from qluent_cli.formatters._common import (
    fmt_date,
    fmt_driver_summary,
    fmt_num,
    fmt_pct,
    fmt_share,
    fmt_share_delta,
    fmt_window,
)


def _fmt_conclusion(conclusion: dict[str, Any], lines: list[str]) -> None:
    confidence_score = conclusion.get("confidence_score")
    confidence_line = f"  Evidence confidence: {conclusion['confidence']}"
    if confidence_score is not None:
        confidence_line += f" (coverage score {confidence_score * 100:.0f}%)"
    lines.append(confidence_line)
    if conclusion.get("confidence_description"):
        lines.append(f"  {conclusion['confidence_description']}")
    if conclusion.get("evidence_types_present"):
        lines.append(
            "  Evidence present: "
            + ", ".join(conclusion["evidence_types_present"])
        )
    if conclusion.get("evidence_types_missing"):
        lines.append(
            "  Evidence missing: "
            + ", ".join(conclusion["evidence_types_missing"])
        )

    takeaways = conclusion.get("takeaways", [])
    if takeaways:
        lines.append("")
        lines.append("  Top takeaways:")
        for index, takeaway in enumerate(takeaways[:5], start=1):
            lines.append(f"    {index}. {takeaway['summary']}")

    unresolved = conclusion.get("unresolved_nodes", [])
    if unresolved:
        lines.append("")
        lines.append("  Unresolved branches:")
        for item in unresolved[:3]:
            lines.append(f"    - {item['summary']}")


def _fmt_time_slices(data: dict[str, Any], lines: list[str]) -> None:
    time_slices = data.get("time_slices", [])
    if not time_slices:
        return
    lines.append("")
    lines.append(f"  Largest time slices ({data.get('time_slice_grain', 'day')}):")
    ranked_slices = sorted(
        time_slices,
        key=lambda item: abs(item.get("delta_value", 0)),
        reverse=True,
    )
    for slice_result in ranked_slices[:3]:
        summary = (
            f"    {fmt_window(slice_result['current_window'])} vs {fmt_window(slice_result['comparison_window'])}: "
            f"Δ {fmt_num(slice_result['delta_value'], signed=True)} ({fmt_pct(slice_result.get('delta_ratio'))})"
        )
        if slice_result.get("share_of_change") is not None:
            summary += f" | {fmt_share(slice_result['share_of_change'])} of change"
        lines.append(summary)

        top_contributors = slice_result.get("top_contributors", [])
        if top_contributors:
            lines.append("      drivers: " + fmt_driver_summary(top_contributors))


def _fmt_mix_shift(data: dict[str, Any], lines: list[str]) -> None:
    mix_shift = data.get("mix_shift")
    if not mix_shift or not mix_shift.get("segments"):
        return
    lines.append("")
    lines.append(f"  Mix shift ({mix_shift['dimension']}):")
    for segment in mix_shift["segments"][:3]:
        summary = (
            f"    {segment['segment']}: Δ {fmt_num(segment['delta_value'], signed=True)}"
        )
        if (
            segment.get("comparison_share") is not None
            and segment.get("current_share") is not None
        ):
            summary += (
                f" | share {fmt_share(segment['comparison_share'])}"
                f" → {fmt_share(segment['current_share'])}"
                f" ({fmt_share_delta(segment.get('share_delta'))})"
            )
        if segment.get("baseline_effect") is not None:
            summary += f" | baseline {fmt_num(segment['baseline_effect'], signed=True)}"
        if segment.get("mix_effect") is not None:
            summary += f" | mix {fmt_num(segment['mix_effect'], signed=True)}"
        lines.append(summary)


def _fmt_finding(finding: dict[str, Any], lines: list[str]) -> None:
    indent = "    " + ("  " * finding.get("depth", 0))
    summary = (
        f"{finding['label']}: Δ {fmt_num(finding['delta_value'], signed=True)} "
        f"({fmt_pct(finding.get('delta_ratio'))})"
    )
    if finding.get("contribution_value") is not None:
        summary += (
            f" | parent contribution {fmt_num(finding['contribution_value'], signed=True)}"
        )
        if finding.get("contribution_share") is not None:
            summary += f" ({fmt_share(finding['contribution_share'])})"
    lines.append(f"{indent}{summary}")

    direct_contributors = finding.get("direct_contributors", [])
    if direct_contributors:
        lines.append(f"{indent}  child drivers: " + fmt_driver_summary(direct_contributors))

    formula_analysis = finding.get("formula_analysis")
    if formula_analysis and formula_analysis.get("effects"):
        non_zero_effects = [
            effect
            for effect in formula_analysis["effects"]
            if abs(effect.get("effect_value", 0)) > 1e-9
        ]
        visible_effects = non_zero_effects or formula_analysis["effects"][:1]
        effect_parts = [
            f"{effect['label']} {fmt_num(effect['effect_value'], signed=True)}"
            for effect in visible_effects
        ]
        lines.append(f"{indent}  mechanism: " + ", ".join(effect_parts))

    segment_dimension = finding.get("segment_dimension")
    segment_findings = finding.get("segment_findings", [])
    if segment_dimension and segment_findings:
        segment_parts = []
        for segment in segment_findings[:3]:
            part = (
                f"{segment['segment']} {fmt_num(segment['delta_value'], signed=True)}"
            )
            if segment.get("share_of_change") is not None:
                part += f" ({fmt_share(segment['share_of_change'])})"
            else:
                part += f" ({fmt_pct(segment.get('delta_ratio'))})"
            segment_parts.append(part)
        lines.append(
            f"{indent}  best segment cut: {segment_dimension} -> " + ", ".join(segment_parts)
        )


def format_root_cause(data: RCAOutput | dict[str, Any]) -> str:
    """Format root-cause analysis results for human consumption."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    lines = [
        (
            f"{data['tree_label']} RCA — "
            f"{fmt_date(cw['date_from'])}–{fmt_date(cw['date_to'])} vs "
            f"{fmt_date(pw['date_from'])}–{fmt_date(pw['date_to'])}"
        ),
        "",
        (
            f"  {data['tree_label']}: {fmt_num(data['comparison_value'])} → {fmt_num(data['current_value'])}  "
            f"Δ {fmt_num(data['delta_value'], signed=True)} ({fmt_pct(data.get('delta_ratio'))})"
        ),
    ]

    if data.get("dimensions_considered"):
        lines.append(f"  Segment cuts: {', '.join(data['dimensions_considered'])}")

    conclusion = data.get("conclusion")
    if conclusion:
        _fmt_conclusion(conclusion, lines)

    _fmt_time_slices(data, lines)
    _fmt_mix_shift(data, lines)

    findings = data.get("findings", [])
    if findings:
        lines.append("")
        lines.append("  Findings:")
        for finding in findings:
            _fmt_finding(finding, lines)

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        for warning in warnings:
            lines.append(f"    ! {warning}")

    if conclusion and conclusion.get("confidence_factors"):
        lines.append("")
        lines.append("  Evidence factors:")
        for factor in conclusion["confidence_factors"]:
            lines.append(f"    - {factor}")

    return "\n".join(lines)
