"""Metric tree commands — list, match, evaluate, trend, compare, investigate."""

from __future__ import annotations

import json
from datetime import date as dt_date
from typing import Any

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import (
    format_comparison,
    format_evaluation,
    format_investigation,
    format_levers,
    format_period_label,
    format_trend,
    format_tree_detail,
    format_tree_list,
    format_tree_match,
    format_tree_validation,
)
from qluent_cli.utils import parse_filters, resolve_date_args


@click.group()
def trees() -> None:
    """Metric tree commands."""


_DEFAULT_LEVER_SCENARIOS = (0.01, 0.05, 0.10)
_LEVER_KEYWORDS = (
    "elasticity",
    "sensitivity",
    "lever",
    "levers",
    "impact",
    "what if",
    "what-if",
    "scenario",
    "scenarios",
    "if we",
    "increase",
    "decrease",
)


def _is_lever_question(question: str | None) -> bool:
    if not question:
        return False
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in _LEVER_KEYWORDS)


def _build_lever_analysis(
    evaluation: dict[str, Any],
    *,
    top_n: int,
    scenarios: tuple[float, ...] | list[float],
) -> dict[str, Any] | None:
    """Build a deterministic lever summary from evaluation elasticities."""
    if not evaluation:
        return None

    current_root_value = evaluation.get("current_value")
    if not isinstance(current_root_value, (int, float)):
        return None

    deduped_scenarios: list[float] = []
    seen_scenarios: set[float] = set()
    for scenario in scenarios:
        scenario_value = float(scenario)
        if scenario_value <= 0 or scenario_value in seen_scenarios:
            continue
        seen_scenarios.add(scenario_value)
        deduped_scenarios.append(scenario_value)
    if not deduped_scenarios:
        deduped_scenarios = list(_DEFAULT_LEVER_SCENARIOS)

    root_node_id = evaluation.get("root_node_id")
    ranked_levers: list[tuple[float, dict[str, Any]]] = []
    for node in evaluation.get("nodes") or []:
        node_id = node.get("id")
        elasticity = node.get("elasticity")
        if node_id == root_node_id or elasticity is None:
            continue
        if not isinstance(elasticity, (int, float)):
            continue

        recommended_direction = "neutral"
        if elasticity > 0:
            recommended_direction = "increase"
        elif elasticity < 0:
            recommended_direction = "decrease"

        scenario_impacts = [
            {
                "node_change_ratio": scenario,
                "estimated_root_delta_ratio": elasticity * scenario,
                "estimated_root_delta_value": current_root_value * elasticity * scenario,
            }
            for scenario in deduped_scenarios
        ]

        ranked_levers.append(
            (
                abs(elasticity),
                {
                    "node_id": node_id,
                    "label": node.get("label") or node_id,
                    "current_value": node.get("current_value"),
                    "delta_value": node.get("delta_value"),
                    "delta_ratio": node.get("delta_ratio"),
                    "sensitivity": node.get("sensitivity"),
                    "elasticity": elasticity,
                    "recommended_direction": recommended_direction,
                    "scenario_impacts": scenario_impacts,
                },
            )
        )

    ranked_levers.sort(key=lambda item: item[0], reverse=True)
    top_levers = [item[1] for item in ranked_levers[:top_n]]

    warnings: list[str] = []
    if not top_levers:
        warnings.append("No non-root nodes had defined elasticities for this tree.")
    warnings.append(
        "Lever impacts are local linear estimates based on current elasticities; treat them as directional guidance, not forecasts."
    )

    return {
        "tree_id": evaluation.get("tree_id"),
        "tree_label": evaluation.get("tree_label"),
        "root_node_id": root_node_id,
        "current_window": evaluation.get("current_window"),
        "comparison_window": evaluation.get("comparison_window"),
        "current_value": current_root_value,
        "comparison_value": evaluation.get("comparison_value"),
        "delta_value": evaluation.get("delta_value"),
        "delta_ratio": evaluation.get("delta_ratio"),
        "scenarios": deduped_scenarios,
        "top_levers": top_levers,
        "warnings": warnings,
    }


def _collect_lever_findings(bundle: dict[str, Any]) -> list[str]:
    """Summarize the strongest available lever signals."""
    levers = bundle.get("levers") or {}
    top_levers = levers.get("top_levers") or []
    if not top_levers:
        return []

    scenario_lookup = {}
    for impact in top_levers[0].get("scenario_impacts") or []:
        scenario_lookup[impact.get("node_change_ratio")] = impact
    preferred_scenario = scenario_lookup.get(0.05)
    if preferred_scenario is None:
        preferred_scenario = (top_levers[0].get("scenario_impacts") or [None])[0]
    if preferred_scenario is None:
        return []

    label = top_levers[0].get("label") or top_levers[0].get("node_id") or "Unknown"
    elasticity = top_levers[0].get("elasticity")
    change_ratio = preferred_scenario.get("node_change_ratio", 0)
    root_ratio = preferred_scenario.get("estimated_root_delta_ratio", 0)
    root_value = preferred_scenario.get("estimated_root_delta_value", 0)
    return [
        f"{label} is the biggest lever (ε {elasticity:+.2f}); +{change_ratio * 100:.0f}% implies root {root_ratio * 100:+.1f}% (Δ {root_value:+.0f})."
    ]


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
    result = client.match_tree(question)

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
@click.option("--period", "-p", default=None, help='Period like "last week", "this month", "last 30 days"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--top", default=5, type=click.IntRange(1, 20), help="Number of top levers to show")
@click.option(
    "--scenario",
    "scenarios",
    multiple=True,
    type=click.FloatRange(0.0, 1.0),
    default=_DEFAULT_LEVER_SCENARIOS,
    help="Node change ratio to evaluate, expressed as a decimal (repeatable, e.g. 0.05 for +5%)",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def levers(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    top: int,
    scenarios: tuple[float, ...],
    as_json: bool,
) -> None:
    """Quantify top lever impacts from tree elasticities."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    client = QluentClient(load_config())
    evaluation = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)
    data = _build_lever_analysis(evaluation, top_n=top, scenarios=scenarios)
    if data is None:
        raise click.ClickException("Could not compute lever analysis from the evaluation result.")

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_levers(data))


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
    help="Natural-language investigation prompt. The server will match the best tree and infer windows unless you override them.",
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
    if bool(tree_id) == bool(question):
        raise click.UsageError("Provide either TREE_ID or --question.")

    client = QluentClient(load_config())
    parsed_filters = parse_filters(filters)

    # When using --question, resolve the tree via server-side matching first
    if question and not tree_id:
        match_result = client.match_tree(question)
        if match_result.get("matched") and match_result.get("tree_id"):
            tree_id = str(match_result["tree_id"])
        else:
            # Return the match result as-is so the caller can see candidates
            bundle = {
                "question": question,
                "match": match_result,
                "tree_id": None,
                "agent": {
                    "status": "needs_tree_selection",
                    "top_findings": [],
                    "gaps": ["No unambiguous tree match. See match.top_candidates."],
                    "recommended_next_steps": [],
                },
            }
            if as_json:
                click.echo(json.dumps(bundle, indent=2))
            else:
                click.echo(format_investigation(bundle))
            return

    assert tree_id is not None
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)

    # Delegate full investigation to server
    bundle = client.investigate_tree(
        tree_id,
        c_from,
        c_to,
        p_from,
        p_to,
        question=question,
        trend_periods=trend_periods,
        trend_grain=trend_grain,
        trend_as_of=trend_as_of,
        segment_by=list(segment_by),
        filters=parsed_filters,
        compare_trees=list(compare_trees),
        max_depth=max_depth,
        max_branching=max_branches,
        max_segments=max_segments,
        min_contribution_share=min_contribution_share,
    )

    if as_json:
        click.echo(json.dumps(bundle, indent=2))
    else:
        click.echo(format_investigation(bundle))
