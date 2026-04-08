"""Metric tree commands — list, match, evaluate, trend, compare, investigate."""

from __future__ import annotations

import json
import shlex
from datetime import date as dt_date
from typing import Any

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import (
    format_comparison,
    format_evaluation,
    format_investigation,
    format_period_label,
    format_trend,
    format_tree_detail,
    format_tree_list,
    format_tree_match,
    format_tree_validation,
)
from qluent_cli.matching import match_tree_question
from qluent_cli.utils import format_step_error, parse_filters, resolve_date_args


@click.group()
def trees() -> None:
    """Metric tree commands."""


def _collect_trend_evaluations(
    client: QluentClient,
    tree_id: str,
    periods: int,
    grain: str,
    as_of: str | None,
) -> list[dict[str, Any]]:
    from qluent_cli.dates import generate_consecutive_windows

    ref_date = dt_date.fromisoformat(as_of) if as_of else None
    window_pairs = generate_consecutive_windows(periods, grain, today=ref_date)
    evaluations: list[dict[str, Any]] = []
    for window_pair in window_pairs:
        data = client.evaluate_tree(
            tree_id,
            str(window_pair.current.date_from),
            str(window_pair.current.date_to),
            str(window_pair.comparison.date_from),
            str(window_pair.comparison.date_to),
        )
        evaluations.append(data)
    return evaluations


def _resolve_investigation_input(
    client: QluentClient,
    tree_id: str | None,
    question: str | None,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
) -> tuple[str | None, dict[str, Any] | None, str, str, str, str]:
    """Resolve investigation target plus evaluation windows."""
    if bool(tree_id) == bool(question):
        raise click.UsageError("Provide either TREE_ID or --question.")

    if question:
        try:
            tree_collection = client.list_trees()
        except Exception as exc:
            raise click.ClickException(
                "Failed to load metric trees for question matching: "
                + format_step_error(exc)
            ) from exc

        match_result = match_tree_question(question, tree_collection)
        if current_range or compare_range or period:
            c_from, c_to, p_from, p_to = resolve_date_args(
                period,
                current_range,
                compare_range,
            )
        else:
            current_window = match_result["current_window"]
            comparison_window = match_result["comparison_window"]
            c_from = current_window["date_from"]
            c_to = current_window["date_to"]
            p_from = comparison_window["date_from"]
            p_to = comparison_window["date_to"]

        resolved_tree_id = (
            str(match_result.get("tree_id"))
            if match_result.get("matched") and match_result.get("tree_id")
            else None
        )
        return resolved_tree_id, match_result, c_from, c_to, p_from, p_to

    assert tree_id is not None
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    return tree_id, None, c_from, c_to, p_from, p_to


def _period_command_args(c_from: str, c_to: str, p_from: str, p_to: str) -> list[str]:
    return [
        "--current",
        f"{c_from}:{c_to}",
        "--compare",
        f"{p_from}:{p_to}",
    ]


def _agent_command(parts: list[str]) -> str:
    return shlex.join(parts)


def _add_recommendation(
    recommendations: list[dict[str, str]],
    *,
    kind: str,
    title: str,
    why: str,
    command: str,
) -> None:
    if any(item.get("command") == command for item in recommendations):
        return
    recommendations.append(
        {
            "kind": kind,
            "title": title,
            "why": why,
            "command": command,
        }
    )


def _collect_agent_top_findings(bundle: dict[str, Any]) -> list[str]:
    """Summarize the strongest available evidence for an investigation."""
    findings: list[str] = []

    root_cause = bundle.get("root_cause") or {}
    conclusion = root_cause.get("conclusion") or {}
    for takeaway in conclusion.get("takeaways") or []:
        summary = takeaway.get("summary")
        if summary:
            findings.append(str(summary))
        if len(findings) >= 3:
            return findings
    if findings:
        return findings

    evaluation = bundle.get("evaluation") or {}
    for contributor in evaluation.get("top_contributors") or []:
        label = contributor.get("label") or contributor.get("node_id") or "Unknown"
        delta_value = contributor.get("delta_value")
        delta_share = contributor.get("delta_share")
        summary = f"{label} drove Δ {delta_value}"
        if delta_share is not None:
            summary += f" ({delta_share:.0%} of change)"
        findings.append(summary)
        if len(findings) >= 3:
            return findings

    if evaluation:
        tree_label = evaluation.get("tree_label", bundle.get("tree_label", bundle.get("tree_id", "Metric")))
        findings.append(
            f"{tree_label} moved from {evaluation.get('comparison_value')} to {evaluation.get('current_value')} "
            f"(Δ {evaluation.get('delta_value')})."
        )

    return findings[:3]


def _collect_agent_gaps(bundle: dict[str, Any]) -> list[str]:
    """Highlight the main evidence gaps or blockers for an investigation."""
    raw_gaps: list[str] = []
    match_result = bundle.get("match") or {}
    validation = bundle.get("validation") or {}
    root_cause = bundle.get("root_cause") or {}
    conclusion = root_cause.get("conclusion") or {}
    step_errors = bundle.get("step_errors") or {}

    if bundle.get("question") and not bundle.get("tree_id"):
        decision = match_result.get("decision")
        if decision == "ambiguous":
            raw_gaps.append("Question matched multiple saved trees and needs an explicit tree choice.")
        elif decision == "no_trees":
            raw_gaps.append("No metric trees are configured for this project yet.")
        else:
            raw_gaps.append("No saved metric tree matched the investigation question.")

    if validation and not validation.get("valid", True):
        raw_gaps.extend(str(error) for error in (validation.get("errors") or [])[:3])

    supported_dimensions = validation.get("supported_dimensions") or []
    if bundle.get("tree_id") and not bundle.get("segment_by_used") and supported_dimensions:
        raw_gaps.append(
            "No segment cuts were applied. Available dimensions: "
            + ", ".join(str(value) for value in supported_dimensions[:3])
        )

    if bundle.get("tree_id") and not root_cause:
        raw_gaps.append("Root-cause analysis did not return results for this investigation.")

    if root_cause and not conclusion:
        raw_gaps.append("Root-cause analysis returned evidence without a ranked deterministic conclusion.")

    if conclusion.get("evidence_types_missing"):
        raw_gaps.append(
            "Missing deterministic evidence: "
            + ", ".join(str(value) for value in conclusion["evidence_types_missing"])
        )

    for unresolved in conclusion.get("unresolved_nodes") or []:
        summary = unresolved.get("summary")
        if summary:
            raw_gaps.append(str(summary))

    warnings = root_cause.get("warnings") or []
    if warnings:
        raw_gaps.extend(str(warning) for warning in warnings[:3])

    for key, message in step_errors.items():
        raw_gaps.append(f"{key.replace('_', ' ')} step error: {message}")

    deduped: list[str] = []
    seen: set[str] = set()
    for gap in raw_gaps:
        cleaned = gap.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped[:6]


def _derive_agent_status(bundle: dict[str, Any]) -> str:
    """Classify investigation completeness for agentic follow-up."""
    if bundle.get("question") and not bundle.get("tree_id"):
        return "needs_tree_selection"

    validation = bundle.get("validation") or {}
    root_cause = bundle.get("root_cause") or {}
    conclusion = root_cause.get("conclusion") or {}
    step_errors = bundle.get("step_errors") or {}

    if not root_cause:
        return "needs_more_data"

    if (
        not validation.get("valid", True)
        or step_errors
        or not conclusion
        or conclusion.get("evidence_types_missing")
        or conclusion.get("unresolved_nodes")
        or root_cause.get("warnings")
    ):
        return "partially_resolved"

    return "resolved"


_REVENUE_PLAYBOOK = [
    (
        "order_volume",
        "Check whether the change is primarily driven by order volume rather than basket size.",
    ),
    (
        "net_revenue",
        "Check whether refunds or discounting explain the difference between gross and net performance.",
    ),
    (
        "blended_roas",
        "Check whether paid spend efficiency or budget changes are amplifying the revenue movement.",
    ),
]


def _recommend_tree_selection(
    recommendations: list[dict[str, str]],
    match_result: dict[str, Any],
    question: str,
    period_args: list[str],
) -> None:
    """Add tree-selection recommendations when no unambiguous tree was found."""
    top_candidates = match_result.get("top_candidates") or []
    best_candidate = next(
        (
            str(candidate.get("tree_id"))
            for candidate in top_candidates
            if candidate.get("tree_id")
        ),
        None,
    )
    if best_candidate:
        _add_recommendation(
            recommendations,
            kind="tree_selection",
            title=f"Investigate {best_candidate}",
            why="Run the strongest candidate explicitly when the question does not resolve to one unambiguous tree.",
            command=_agent_command(
                ["qluent", "trees", "investigate", best_candidate, *period_args, "--json-output"]
            ),
        )
    _add_recommendation(
        recommendations,
        kind="tree_discovery",
        title="Review saved trees",
        why="Inspect available tree ids and labels before forcing a manual tree selection.",
        command=_agent_command(["qluent", "trees", "list", "--json-output"]),
    )
    _add_recommendation(
        recommendations,
        kind="tree_match",
        title="Inspect tree match candidates",
        why="Look at match scores and candidate reasons directly if you want to tune the selection logic or choose manually.",
        command=_agent_command(["qluent", "trees", "match", question, "--json-output"]),
    )


def _recommend_revenue_comparisons(
    recommendations: list[dict[str, str]],
    tree_id: str,
    tree_label: str,
    compare_trees: tuple[str, ...],
    period_args: list[str],
) -> None:
    """Add revenue-playbook comparison recommendations if the tree looks revenue-related."""
    revenue_like = "revenue" in tree_id.lower() or "revenue" in tree_label
    if not revenue_like:
        return
    existing_compare_targets = {tree_id, *compare_trees}
    for compare_tree_id, why in _REVENUE_PLAYBOOK:
        if compare_tree_id in existing_compare_targets:
            continue
        _add_recommendation(
            recommendations,
            kind="comparison",
            title=f"Compare against {compare_tree_id}",
            why=why,
            command=_agent_command(
                ["qluent", "trees", "compare", tree_id, compare_tree_id, *period_args, "--json-output"]
            ),
        )
        if len(recommendations) >= 4:
            break


def _build_recommended_next_steps(
    bundle: dict[str, Any],
    *,
    compare_trees: tuple[str, ...],
) -> list[dict[str, str]]:
    """Emit deterministic follow-up commands that an agent can execute next."""
    recommendations: list[dict[str, str]] = []
    tree_id = bundle.get("tree_id")
    question = bundle.get("question")
    match_result = bundle.get("match") or {}
    validation = bundle.get("validation") or {}
    root_cause = bundle.get("root_cause") or {}
    trend = bundle.get("trend") or {}
    c_from = bundle["current_window"]["date_from"]
    c_to = bundle["current_window"]["date_to"]
    p_from = bundle["comparison_window"]["date_from"]
    p_to = bundle["comparison_window"]["date_to"]
    period_args = _period_command_args(c_from, c_to, p_from, p_to)

    if question and not tree_id:
        _recommend_tree_selection(recommendations, match_result, question, period_args)
        return recommendations[:3]

    assert tree_id is not None
    tree_label = str(bundle.get("tree_label") or tree_id).lower()
    segment_by_used = list(bundle.get("segment_by_used") or [])
    supported_dimensions = [str(value) for value in (validation.get("supported_dimensions") or [])]

    if not validation or not validation.get("valid", True):
        _add_recommendation(
            recommendations,
            kind="validation",
            title="Validate tree contract",
            why="Confirm the saved metric tree exposes the dimensions and execution columns required for reliable RCA.",
            command=_agent_command(["qluent", "trees", "validate", tree_id, "--json-output"]),
        )

    segment_dimensions = segment_by_used or supported_dimensions[:2]
    segment_args: list[str] = []
    for dimension in segment_dimensions:
        segment_args.extend(["--segment-by", dimension])

    if not root_cause:
        _add_recommendation(
            recommendations,
            kind="root_cause",
            title="Run standalone RCA",
            why="Retry the deterministic RCA step directly to isolate whether the failure is in the bundled investigation or the root-cause endpoint itself.",
            command=_agent_command(
                ["qluent", "rca", "analyze", tree_id, *period_args, *segment_args, "--json-output"]
            ),
        )

    if supported_dimensions and not segment_by_used:
        _add_recommendation(
            recommendations,
            kind="segmentation",
            title="Add segment cuts",
            why="Segment evidence is available on this tree but was not used in the investigation bundle.",
            command=_agent_command(
                ["qluent", "rca", "analyze", tree_id, *period_args, *segment_args, "--json-output"]
            ),
        )

    if not (trend.get("evaluations") or []):
        _add_recommendation(
            recommendations,
            kind="trend",
            title="Backfill recent trend context",
            why="Trend context helps distinguish a one-period shock from a longer-running decline or recovery.",
            command=_agent_command(["qluent", "trees", "trend", tree_id, "--periods", "4", "--grain", "week", "--json-output"]),
        )

    _recommend_revenue_comparisons(
        recommendations, tree_id, tree_label, compare_trees, period_args
    )

    return recommendations[:4]


def _init_investigation_bundle(
    *,
    question: str | None,
    match_result: dict[str, Any] | None,
    resolved_tree_id: str | None,
    period_label: str,
    c_from: str,
    c_to: str,
    p_from: str,
    p_to: str,
    parsed_filters: dict[str, list[str]],
    segment_by: tuple[str, ...],
    trend_grain: str,
    trend_periods: int,
    trend_as_of: str | None,
) -> dict[str, Any]:
    """Create the initial investigation bundle dict."""
    return {
        "question": question,
        "match": match_result,
        "tree_id": resolved_tree_id,
        "tree_label": match_result.get("tree_label") if match_result else resolved_tree_id,
        "period_label": period_label,
        "current_window": {"date_from": c_from, "date_to": c_to},
        "comparison_window": {"date_from": p_from, "date_to": p_to},
        "filters": parsed_filters,
        "segment_by_requested": list(segment_by),
        "segment_by_used": [],
        "validation": None,
        "trend": {
            "grain": trend_grain,
            "periods": trend_periods,
            "as_of": trend_as_of,
            "evaluations": [],
        },
        "evaluation": None,
        "root_cause": None,
        "comparison": {
            "period_label": period_label,
            "results": [],
            "errors": {},
        },
        "step_errors": {},
        "agent": {
            "status": "needs_more_data",
            "top_findings": [],
            "gaps": [],
            "recommended_next_steps": [],
        },
    }


def _run_investigation_steps(
    *,
    client: QluentClient,
    bundle: dict[str, Any],
    resolved_tree_id: str,
    c_from: str,
    c_to: str,
    p_from: str,
    p_to: str,
    segment_by: tuple[str, ...],
    parsed_filters: dict[str, list[str]],
    trend_periods: int,
    trend_grain: str,
    trend_as_of: str | None,
    compare_trees: tuple[str, ...],
    max_depth: int,
    max_branches: int,
    max_segments: int,
    min_contribution_share: float,
) -> None:
    """Execute validation, trend, evaluation, RCA, and comparison steps."""
    validation = None
    try:
        validation = client.validate_tree(resolved_tree_id)
        bundle["validation"] = validation
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["validation"] = format_step_error(exc)

    try:
        trend_evaluations = _collect_trend_evaluations(
            client,
            resolved_tree_id,
            trend_periods,
            trend_grain,
            trend_as_of,
        )
        bundle["trend"]["evaluations"] = trend_evaluations
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["trend"] = format_step_error(exc)

    try:
        evaluation = client.evaluate_tree(resolved_tree_id, c_from, c_to, p_from, p_to)
        bundle["evaluation"] = evaluation
        bundle["tree_label"] = evaluation.get("tree_label", resolved_tree_id)
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["evaluation"] = format_step_error(exc)

    segment_by_used = list(segment_by)
    if not segment_by_used and validation:
        segment_by_used = list(validation.get("supported_dimensions") or [])[:2]
    bundle["segment_by_used"] = segment_by_used

    try:
        root_cause = client.root_cause_tree(
            resolved_tree_id,
            c_from,
            c_to,
            p_from,
            p_to,
            segment_by=segment_by_used,
            filters=parsed_filters,
            max_depth=max_depth,
            max_branching=max_branches,
            max_segments=max_segments,
            min_contribution_share=min_contribution_share,
        )
        bundle["root_cause"] = root_cause
        if not bundle.get("tree_label"):
            bundle["tree_label"] = root_cause.get("tree_label", resolved_tree_id)
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["root_cause"] = format_step_error(exc)

    for compare_tree_id in compare_trees:
        try:
            comparison_result = client.evaluate_tree(compare_tree_id, c_from, c_to, p_from, p_to)
            bundle["comparison"]["results"].append(comparison_result)
        except Exception as exc:  # pragma: no cover - defensive integration handling
            bundle["comparison"]["errors"][compare_tree_id] = format_step_error(exc)


def _finalize_agent_summary(
    bundle: dict[str, Any],
    *,
    compare_trees: tuple[str, ...],
) -> None:
    """Compute and attach the agent summary to the bundle."""
    bundle["agent"] = {
        "status": _derive_agent_status(bundle),
        "top_findings": _collect_agent_top_findings(bundle),
        "gaps": _collect_agent_gaps(bundle),
        "recommended_next_steps": _build_recommended_next_steps(
            bundle,
            compare_trees=compare_trees,
        ),
    }


@trees.command(name="list")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def list_trees(as_json: bool) -> None:
    """List available metric trees."""
    client = QluentClient(load_config())
    data = client.list_trees()

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_list(data))


@trees.command()
@click.argument("question")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def match(question: str, as_json: bool) -> None:
    """Match a natural-language question to the best saved metric tree."""
    client = QluentClient(load_config())
    data = client.list_trees()
    result = match_tree_question(question, data)

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(format_tree_match(result))


@trees.command()
@click.argument("tree_id")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def get(tree_id: str, as_json: bool) -> None:
    """Show the structure of a metric tree."""
    client = QluentClient(load_config())
    data = client.get_tree(tree_id)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_detail(data))


@trees.command()
@click.argument("tree_id")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def validate(tree_id: str, as_json: bool) -> None:
    """Validate a saved metric tree against its referenced metric SQL."""
    client = QluentClient(load_config())
    data = client.validate_tree(tree_id)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_validation(data))


@trees.command()
@click.argument("tree_id")
@click.option("--period", "-p", default=None, help='Period like "last week", "this month", "last 30 days"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def evaluate(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    as_json: bool,
) -> None:
    """Evaluate a metric tree over date windows."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    client = QluentClient(load_config())
    data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_evaluation(data))


@trees.command()
@click.argument("tree_id")
@click.option("--periods", "-n", default=4, type=click.IntRange(1, 52), help="Number of consecutive periods (default: 4)")
@click.option("--grain", "-g", default="week", type=click.Choice(["week", "month"]), help="Period granularity")
@click.option("--as-of", "as_of", default=None, help="Reference date as YYYY-MM-DD (default: today)")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def trend(tree_id: str, periods: int, grain: str, as_of: str | None, as_json: bool) -> None:
    """Show multi-period trend for a metric tree."""
    client = QluentClient(load_config())
    evaluations = _collect_trend_evaluations(client, tree_id, periods, grain, as_of)

    if as_json:
        click.echo(json.dumps(evaluations, indent=2))
    else:
        tree_label = evaluations[0].get("tree_label", tree_id) if evaluations else tree_id
        click.echo(format_trend(tree_label, evaluations, grain))


@trees.command()
@click.argument("tree_ids", nargs=-1, required=True)
@click.option("--period", "-p", default=None, help='Period like "last week", "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def compare(
    tree_ids: tuple[str, ...],
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    as_json: bool,
) -> None:
    """Compare multiple metric trees side by side for the same period."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)

    client = QluentClient(load_config())
    results: list[tuple[str, dict[str, Any]]] = []
    for tree_id in tree_ids:
        data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)
        results.append((data.get("tree_label", tree_id), data))

    if as_json:
        click.echo(json.dumps([data for _, data in results], indent=2))
    else:
        click.echo(format_comparison(results, format_period_label(c_from, c_to, p_from, p_to)))


@trees.command()
@click.argument("tree_id", required=False)
@click.option(
    "--question",
    default=None,
    help="Natural-language investigation prompt. The CLI will match the best tree and infer windows unless you override them.",
)
@click.option("--period", "-p", default=None, help='Period like "last week" or "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--trend-periods", default=4, type=click.IntRange(1, 52), help="Number of periods for the bundled trend step")
@click.option("--trend-grain", default="week", type=click.Choice(["week", "month"]), help="Granularity for the bundled trend step")
@click.option("--trend-as-of", default=None, help="Reference date for bundled trend as YYYY-MM-DD")
@click.option("--segment-by", "segment_by", multiple=True, help="Dimension to consider for segment RCA (repeatable)")
@click.option("--filter", "filters", multiple=True, help="Filter as dimension=value (repeatable)")
@click.option("--compare-tree", "compare_trees", multiple=True, help="Additional tree to compare against the primary tree")
@click.option("--max-depth", default=3, type=click.IntRange(1, 6), help="Maximum tree depth to traverse in RCA")
@click.option("--max-branches", default=2, type=click.IntRange(1, 10), help="Maximum child branches to follow per node in RCA")
@click.option("--max-segments", default=5, type=click.IntRange(1, 20), help="Maximum segments to show per node in RCA")
@click.option(
    "--min-contribution-share",
    default=0.1,
    type=click.FloatRange(0.0, 1.0),
    help="Minimum absolute direct contribution share required to follow a child branch in RCA",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def investigate(
    tree_id: str | None,
    question: str | None,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    trend_periods: int,
    trend_grain: str,
    trend_as_of: str | None,
    segment_by: tuple[str, ...],
    filters: tuple[str, ...],
    compare_trees: tuple[str, ...],
    max_depth: int,
    max_branches: int,
    max_segments: int,
    min_contribution_share: float,
    as_json: bool,
) -> None:
    """Run a deterministic multi-step investigation bundle for one tree or question."""
    parsed_filters = parse_filters(filters)

    client = QluentClient(load_config())
    resolved_tree_id, match_result, c_from, c_to, p_from, p_to = _resolve_investigation_input(
        client,
        tree_id,
        question,
        period,
        current_range,
        compare_range,
    )
    period_label = format_period_label(c_from, c_to, p_from, p_to)
    bundle = _init_investigation_bundle(
        question=question,
        match_result=match_result,
        resolved_tree_id=resolved_tree_id,
        period_label=period_label,
        c_from=c_from,
        c_to=c_to,
        p_from=p_from,
        p_to=p_to,
        parsed_filters=parsed_filters,
        segment_by=segment_by,
        trend_grain=trend_grain,
        trend_periods=trend_periods,
        trend_as_of=trend_as_of,
    )

    if resolved_tree_id:
        _run_investigation_steps(
            client=client,
            bundle=bundle,
            resolved_tree_id=resolved_tree_id,
            c_from=c_from,
            c_to=c_to,
            p_from=p_from,
            p_to=p_to,
            segment_by=segment_by,
            parsed_filters=parsed_filters,
            trend_periods=trend_periods,
            trend_grain=trend_grain,
            trend_as_of=trend_as_of,
            compare_trees=compare_trees,
            max_depth=max_depth,
            max_branches=max_branches,
            max_segments=max_segments,
            min_contribution_share=min_contribution_share,
        )

    _finalize_agent_summary(bundle, compare_trees=compare_trees)

    if as_json:
        click.echo(json.dumps(bundle, indent=2))
    else:
        click.echo(format_investigation(bundle))
