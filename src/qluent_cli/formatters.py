"""Human-readable output formatting for metric tree results."""

from __future__ import annotations

import re
from datetime import date as dt_date
from typing import Any


def _fmt_num(value: float, signed: bool = False) -> str:
    """Format a number with commas and optional sign."""
    if abs(value) >= 1:
        formatted = f"{abs(value):,.0f}"
    else:
        formatted = f"{abs(value):,.2f}"
    if signed:
        prefix = "+" if value >= 0 else "-"
        return f"{prefix}{formatted}"
    if value < 0:
        return f"-{formatted}"
    return formatted


def _fmt_pct(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio * 100:+.1f}%"


def _fmt_share(share: float | None) -> str:
    if share is None:
        return "n/a"
    return f"{share * 100:.0f}%"


def _fmt_elasticity(elasticity: float | None) -> str:
    if elasticity is None:
        return "n/a"
    return f"{elasticity:+.2f}"


def _fmt_direction(direction: str | None) -> str:
    return direction or "neutral"


def _fmt_share_delta(share: float | None) -> str:
    if share is None:
        return "n/a"
    return f"{share * 100:+.0f}pp"


def _fmt_date(d: str) -> str:
    """Format ISO date as short form: Mar 10."""
    parsed = dt_date.fromisoformat(d)
    return f"{parsed:%b} {parsed.day}"


def _fmt_window(window: dict[str, str]) -> str:
    if window["date_from"] == window["date_to"]:
        return _fmt_date(window["date_from"])
    return f"{_fmt_date(window['date_from'])}–{_fmt_date(window['date_to'])}"


def format_period_label(c_from: str, c_to: str, p_from: str, p_to: str) -> str:
    """Format a period comparison label like 'Mar 10-Mar 16 vs Mar 3-Mar 9'."""
    return f"{_fmt_date(c_from)}–{_fmt_date(c_to)} vs {_fmt_date(p_from)}–{_fmt_date(p_to)}"


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


def format_tree_match(data: dict[str, Any]) -> str:
    """Format natural-language tree matching output."""
    current_window = data["current_window"]
    comparison_window = data["comparison_window"]
    lines = [f'Question: "{data["question"]}"', ""]

    if data.get("matched"):
        lines.append(
            f"Matched tree: {data['tree_id']} ({data.get('tree_label') or data['tree_id']})"
        )
        lines.append(f"  Score: {data.get('score', 0)}")
        reasons = data.get("reasons") or []
        if reasons:
            lines.append("  Reasons:")
            for reason in reasons:
                lines.append(f"    - {reason}")
    else:
        decision = data.get("decision") or "no_match"
        if decision == "ambiguous":
            lines.append("No unambiguous tree match.")
        elif decision == "no_trees":
            lines.append("No metric trees are configured.")
        else:
            lines.append("No tree match found.")

    lines.append("")
    lines.append(
        "Inferred window: "
        + format_period_label(
            current_window["date_from"],
            current_window["date_to"],
            comparison_window["date_from"],
            comparison_window["date_to"],
        )
    )

    top_candidates = data.get("top_candidates") or []
    if top_candidates:
        lines.append("")
        lines.append("Top candidates:")
        for candidate in top_candidates:
            label = candidate.get("tree_label") or candidate.get("tree_id")
            lines.append(
                f"  {candidate.get('tree_id')} ({label}) — score {candidate.get('score', 0)}"
            )

    return "\n".join(lines)


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
        has_elasticity = any(n.get("elasticity") is not None for n in nodes)
        lines.append("  All nodes:")
        max_label = max(len(n["label"]) for n in nodes) if nodes else 0
        for n in nodes:
            label = n["label"].ljust(max_label)
            line = (
                f"    {label}  "
                f"{_fmt_num(n['comparison_value']):>12} → {_fmt_num(n['current_value']):>12}  "
                f"Δ {_fmt_num(n['delta_value'], signed=True):>12}  {_fmt_pct(n.get('delta_ratio')):>7}"
            )
            if has_elasticity:
                line += f"  ε {_fmt_elasticity(n.get('elasticity')):>6}"
            lines.append(line)

    # Warnings
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
        f"{_fmt_date(cw['date_from'])}–{_fmt_date(cw['date_to'])} vs "
        f"{_fmt_date(pw['date_from'])}–{_fmt_date(pw['date_to'])}"
    )

    lines = [
        header,
        "",
        (
            f"  {data['tree_label']}: {_fmt_num(data['comparison_value'])} → {_fmt_num(data['current_value'])}  "
            f"Δ {_fmt_num(data['delta_value'], signed=True)} ({_fmt_pct(data.get('delta_ratio'))})"
        ),
    ]

    top_levers = data.get("top_levers") or []
    if top_levers:
        lines.extend(["", "  Top levers:"])
        for lever in top_levers:
            lines.append(
                f"    {lever['label']}  ε {_fmt_elasticity(lever.get('elasticity')):>6}  "
                f"best action: {_fmt_direction(lever.get('recommended_direction'))}"
            )
            for impact in lever.get("scenario_impacts") or []:
                lines.append(
                    f"      +{impact['node_change_ratio'] * 100:.0f}% node → "
                    f"root {_fmt_pct(impact.get('estimated_root_delta_ratio'))} "
                    f"(Δ {_fmt_num(impact['estimated_root_delta_value'], signed=True)})"
                )
    else:
        lines.extend(["", "  No non-root nodes had defined elasticities."])

    warnings = data.get("warnings") or []
    if warnings:
        lines.append("")
        for warning in warnings:
            lines.append(f"  ! {warning}")

    return "\n".join(lines)


def _fmt_driver_summary(contributors: list[dict[str, Any]]) -> str:
    """Format a list of contributors into a comma-separated driver summary."""
    parts = []
    for contributor in contributors:
        part = f"{contributor['label']} {_fmt_num(contributor['delta_value'], signed=True)}"
        if contributor.get("delta_share") is not None:
            part += f" ({_fmt_share(contributor['delta_share'])})"
        parts.append(part)
    return ", ".join(parts)


def _fmt_rca_conclusion(conclusion: dict[str, Any], lines: list[str]) -> None:
    """Append conclusion section lines for an RCA result."""
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


def _fmt_rca_time_slices(data: dict[str, Any], lines: list[str]) -> None:
    """Append time-slice section lines for an RCA result."""
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
            f"    {_fmt_window(slice_result['current_window'])} vs {_fmt_window(slice_result['comparison_window'])}: "
            f"Δ {_fmt_num(slice_result['delta_value'], signed=True)} ({_fmt_pct(slice_result.get('delta_ratio'))})"
        )
        if slice_result.get("share_of_change") is not None:
            summary += f" | {_fmt_share(slice_result['share_of_change'])} of change"
        lines.append(summary)

        top_contributors = slice_result.get("top_contributors", [])
        if top_contributors:
            lines.append(f"      drivers: " + _fmt_driver_summary(top_contributors))


def _fmt_rca_mix_shift(data: dict[str, Any], lines: list[str]) -> None:
    """Append mix-shift section lines for an RCA result."""
    mix_shift = data.get("mix_shift")
    if not mix_shift or not mix_shift.get("segments"):
        return
    lines.append("")
    lines.append(f"  Mix shift ({mix_shift['dimension']}):")
    for segment in mix_shift["segments"][:3]:
        summary = (
            f"    {segment['segment']}: Δ {_fmt_num(segment['delta_value'], signed=True)}"
        )
        if (
            segment.get("comparison_share") is not None
            and segment.get("current_share") is not None
        ):
            summary += (
                f" | share {_fmt_share(segment['comparison_share'])}"
                f" → {_fmt_share(segment['current_share'])}"
                f" ({_fmt_share_delta(segment.get('share_delta'))})"
            )
        if segment.get("baseline_effect") is not None:
            summary += f" | baseline {_fmt_num(segment['baseline_effect'], signed=True)}"
        if segment.get("mix_effect") is not None:
            summary += f" | mix {_fmt_num(segment['mix_effect'], signed=True)}"
        lines.append(summary)


def _fmt_rca_finding(finding: dict[str, Any], lines: list[str]) -> None:
    """Append a single finding block for an RCA result."""
    indent = "    " + ("  " * finding.get("depth", 0))
    summary = (
        f"{finding['label']}: Δ {_fmt_num(finding['delta_value'], signed=True)} "
        f"({_fmt_pct(finding.get('delta_ratio'))})"
    )
    if finding.get("contribution_value") is not None:
        summary += (
            f" | parent contribution {_fmt_num(finding['contribution_value'], signed=True)}"
        )
        if finding.get("contribution_share") is not None:
            summary += f" ({_fmt_share(finding['contribution_share'])})"
    lines.append(f"{indent}{summary}")

    direct_contributors = finding.get("direct_contributors", [])
    if direct_contributors:
        lines.append(f"{indent}  child drivers: " + _fmt_driver_summary(direct_contributors))

    formula_analysis = finding.get("formula_analysis")
    if formula_analysis and formula_analysis.get("effects"):
        non_zero_effects = [
            effect
            for effect in formula_analysis["effects"]
            if abs(effect.get("effect_value", 0)) > 1e-9
        ]
        visible_effects = non_zero_effects or formula_analysis["effects"][:1]
        effect_parts = [
            f"{effect['label']} {_fmt_num(effect['effect_value'], signed=True)}"
            for effect in visible_effects
        ]
        lines.append(f"{indent}  mechanism: " + ", ".join(effect_parts))

    segment_dimension = finding.get("segment_dimension")
    segment_findings = finding.get("segment_findings", [])
    if segment_dimension and segment_findings:
        segment_parts = []
        for segment in segment_findings[:3]:
            part = (
                f"{segment['segment']} {_fmt_num(segment['delta_value'], signed=True)}"
            )
            if segment.get("share_of_change") is not None:
                part += f" ({_fmt_share(segment['share_of_change'])})"
            else:
                part += f" ({_fmt_pct(segment.get('delta_ratio'))})"
            segment_parts.append(part)
        lines.append(
            f"{indent}  best segment cut: {segment_dimension} -> " + ", ".join(segment_parts)
        )


def format_root_cause(data: dict[str, Any]) -> str:
    """Format root-cause analysis results for human consumption."""
    cw = data["current_window"]
    pw = data["comparison_window"]
    lines = [
        (
            f"{data['tree_label']} RCA — "
            f"{_fmt_date(cw['date_from'])}–{_fmt_date(cw['date_to'])} vs "
            f"{_fmt_date(pw['date_from'])}–{_fmt_date(pw['date_to'])}"
        ),
        "",
        (
            f"  {data['tree_label']}: {_fmt_num(data['comparison_value'])} → {_fmt_num(data['current_value'])}  "
            f"Δ {_fmt_num(data['delta_value'], signed=True)} ({_fmt_pct(data.get('delta_ratio'))})"
        ),
    ]

    if data.get("dimensions_considered"):
        lines.append(f"  Segment cuts: {', '.join(data['dimensions_considered'])}")

    conclusion = data.get("conclusion")
    if conclusion:
        _fmt_rca_conclusion(conclusion, lines)

    _fmt_rca_time_slices(data, lines)
    _fmt_rca_mix_shift(data, lines)

    findings = data.get("findings", [])
    if findings:
        lines.append("")
        lines.append("  Findings:")
        for finding in findings:
            _fmt_rca_finding(finding, lines)

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


def format_tree_validation(data: dict[str, Any]) -> str:
    """Format metric tree contract validation results."""
    status = "valid" if data.get("valid") else "invalid"
    lines = [
        f"{data['tree_label']} Validation",
        "",
        f"  Status: {status}",
    ]
    if data.get("redacted"):
        lines.append(
            f"  {data.get('redaction_reason') or 'Client-safe mode redacted SQL contract details.'}"
        )

    declared_dimensions = data.get("dimensions_declared", [])
    supported_dimensions = data.get("supported_dimensions", [])
    if declared_dimensions:
        lines.append(f"  Declared dimensions: {', '.join(declared_dimensions)}")
        lines.append(
            "  Supported dimensions: "
            + (", ".join(supported_dimensions) if supported_dimensions else "none")
        )

    leaf_nodes = data.get("leaf_nodes", [])
    if leaf_nodes:
        lines.append("")
        lines.append("  Leaf nodes:")
        for leaf in leaf_nodes:
            summary = f"    {leaf['label']} ({leaf['node_id']})"
            if leaf.get("metric_id") is not None:
                summary += f" [metric {leaf.get('metric_id')}]"
            summary += f" [{leaf.get('projection_status', 'explicit')}]"
            lines.append(summary)
            projected_columns = leaf.get("projected_columns", [])
            if projected_columns:
                lines.append(f"      columns: {', '.join(projected_columns)}")
            if leaf.get("missing_columns"):
                lines.append(f"      missing columns: {', '.join(leaf['missing_columns'])}")
            if leaf.get("missing_dimensions"):
                lines.append(f"      missing dimensions: {', '.join(leaf['missing_dimensions'])}")

    errors = data.get("errors", [])
    if errors:
        lines.append("")
        lines.append("  Errors:")
        for error in errors:
            lines.append(f"    ! {error}")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        for warning in warnings:
            lines.append(f"    ! {warning}")

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

    Matches nodes by structural path and only shows a value when the labels line
    up at that path. This avoids silently comparing unrelated nodes.
    """
    if not tree_results:
        return "No data."

    tree_labels = [label for label, _ in tree_results]
    header = " vs ".join(tree_labels) + f" — {period_label}"

    def normalize_label(label: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", label.lower())

    def enumerate_paths(data: dict[str, Any]) -> list[tuple[tuple[int, ...], str, dict[str, Any]]]:
        nodes = data.get("nodes", [])
        if not nodes:
            return []
        nodes_by_id = {node["id"]: node for node in nodes}
        root_id = data.get("root_node_id") or nodes[0]["id"]
        rows: list[tuple[tuple[int, ...], str, dict[str, Any]]] = []

        def walk(node_id: str, path: tuple[int, ...]) -> None:
            node = nodes_by_id.get(node_id)
            if not node:
                return
            rows.append((path, node["label"], node))
            for index, child_id in enumerate(node.get("children", [])):
                walk(child_id, (*path, index))

        walk(root_id, ())
        return rows

    base_paths = enumerate_paths(tree_results[0][1])
    tree_path_maps = []
    for _, data in tree_results:
        tree_path_maps.append({
            path: node
            for path, _label, node in enumerate_paths(data)
        })

    row_labels = [label for _path, label, _node in base_paths]

    # Format
    max_label_len = max(len(la) for la in row_labels) if row_labels else 0
    col_width = max(len(la) for la in tree_labels) + 2
    col_width = max(col_width, 9)

    lines = [header, ""]
    col_header = " " * (max_label_len + 4) + "".join(la.rjust(col_width) for la in tree_labels)
    lines.append(col_header)

    for path, label, _base_node in base_paths:
        padded = label.ljust(max_label_len)
        cells = ""
        base_label_key = normalize_label(label)
        for path_map in tree_path_maps:
            candidate = path_map.get(path)
            if candidate is None:
                cells += "—".rjust(col_width)
                continue

            candidate_label_key = normalize_label(candidate["label"])
            if path and candidate_label_key != base_label_key:
                cells += "—".rjust(col_width)
                continue

            ratio = candidate.get("delta_ratio")
            cells += _fmt_pct(ratio).rjust(col_width) if ratio is not None else "—".rjust(col_width)
        lines.append(f"    {padded}{cells}")

    return "\n".join(lines)


def _fmt_investigation_header(data: dict[str, Any], lines: list[str]) -> str:
    """Append investigation header lines and return the resolved tree label."""
    evaluation = data.get("evaluation") or {}
    validation = data.get("validation") or {}
    root_cause = data.get("root_cause") or {}
    match_result = data.get("match") or {}
    agent = data.get("agent") or {}
    tree_label = (
        evaluation.get("tree_label")
        or validation.get("tree_label")
        or root_cause.get("tree_label")
        or data.get("tree_label")
        or data.get("tree_id", "?")
    )

    lines.extend([f"{tree_label} Investigation", ""])
    if data.get("question"):
        lines.append(f'  Question: "{data["question"]}"')
    if match_result:
        if match_result.get("matched"):
            lines.append(
                "  Matched tree: "
                + str(match_result.get("tree_id") or match_result.get("tree_label") or "?")
            )
        else:
            decision = match_result.get("decision") or "no_match"
            status_label = {
                "ambiguous": "ambiguous match",
                "no_trees": "no saved trees",
            }.get(decision, "no tree match")
            lines.append(f"  Match status: {status_label}")
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


def _fmt_investigation_agent(data: dict[str, Any], lines: list[str]) -> None:
    """Append agent findings, gaps, and recommendations."""
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


def _fmt_investigation_step_results(
    data: dict[str, Any], tree_label: str, lines: list[str]
) -> None:
    """Append validation, trend, evaluation, RCA, and comparison results."""
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
    tree_label = _fmt_investigation_header(data, lines)
    _fmt_investigation_agent(data, lines)
    _fmt_investigation_step_results(data, tree_label, lines)
    return "\n".join(lines)
