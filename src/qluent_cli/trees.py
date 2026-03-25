"""Metric tree commands — list, match, evaluate, trend, compare, investigate."""

from __future__ import annotations

import json
from datetime import date as dt_date
from typing import Any

import click
import httpx

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


@click.group()
def trees() -> None:
    """Metric tree commands."""


def _parse_filters(filter_args: tuple[str, ...]) -> dict[str, list[str]]:
    filters: dict[str, list[str]] = {}
    for raw_filter in filter_args:
        if "=" not in raw_filter:
            raise click.BadParameter(
                f"Invalid filter '{raw_filter}'. Use dimension=value.",
                param_hint="filter",
            )
        key, value = raw_filter.split("=", 1)
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        if not cleaned_key or not cleaned_value:
            raise click.BadParameter(
                f"Invalid filter '{raw_filter}'. Use dimension=value.",
                param_hint="filter",
            )
        filters.setdefault(cleaned_key, []).append(cleaned_value)
    return filters


def _format_step_error(exc: Exception) -> str:
    if isinstance(exc, click.ClickException):
        return exc.message

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            raw_detail = payload.get("error") or payload.get("detail") or payload.get("message")
            if isinstance(raw_detail, dict):
                detail = json.dumps(raw_detail, sort_keys=True)
            elif raw_detail is not None:
                detail = str(raw_detail)
        if not detail:
            detail = response.text.strip()
        if detail:
            return f"{response.status_code} {detail}"
        return f"{response.status_code} {exc}"

    return str(exc)


def _resolve_date_args(
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
) -> tuple[str, str, str, str]:
    """Resolve date arguments into (c_from, c_to, p_from, p_to) strings."""
    from qluent_cli.dates import infer_windows

    if current_range and compare_range:
        c_from, c_to = current_range.split(":")
        p_from, p_to = compare_range.split(":")
    elif current_range:
        c_from, c_to = current_range.split(":")
        windows = infer_windows(f"{c_from} {c_to}")
        p_from = str(windows.comparison.date_from)
        p_to = str(windows.comparison.date_to)
    else:
        period_text = period or "last 7 days"
        windows = infer_windows(period_text)
        c_from = str(windows.current.date_from)
        c_to = str(windows.current.date_to)
        p_from = str(windows.comparison.date_from)
        p_to = str(windows.comparison.date_to)
    return c_from, c_to, p_from, p_to


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
    c_from, c_to, p_from, p_to = _resolve_date_args(period, current_range, compare_range)
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
    c_from, c_to, p_from, p_to = _resolve_date_args(period, current_range, compare_range)

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
@click.argument("tree_id")
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
    tree_id: str,
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
    """Run a deterministic multi-step investigation bundle for one tree."""
    c_from, c_to, p_from, p_to = _resolve_date_args(period, current_range, compare_range)
    parsed_filters = _parse_filters(filters)
    period_label = format_period_label(c_from, c_to, p_from, p_to)

    client = QluentClient(load_config())
    bundle: dict[str, Any] = {
        "tree_id": tree_id,
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
    }

    try:
        validation = client.validate_tree(tree_id)
        bundle["validation"] = validation
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["validation"] = _format_step_error(exc)
        validation = None

    try:
        trend_evaluations = _collect_trend_evaluations(
            client,
            tree_id,
            trend_periods,
            trend_grain,
            trend_as_of,
        )
        bundle["trend"]["evaluations"] = trend_evaluations
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["trend"] = _format_step_error(exc)

    try:
        evaluation = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)
        bundle["evaluation"] = evaluation
        bundle["tree_label"] = evaluation.get("tree_label", tree_id)
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["evaluation"] = _format_step_error(exc)

    segment_by_used = list(segment_by)
    if not segment_by_used and validation:
        segment_by_used = list(validation.get("supported_dimensions") or [])[:2]
    bundle["segment_by_used"] = segment_by_used

    try:
        root_cause = client.root_cause_tree(
            tree_id,
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
            bundle["tree_label"] = root_cause.get("tree_label", tree_id)
    except Exception as exc:  # pragma: no cover - defensive integration handling
        bundle["step_errors"]["root_cause"] = _format_step_error(exc)

    for compare_tree_id in compare_trees:
        try:
            comparison_result = client.evaluate_tree(compare_tree_id, c_from, c_to, p_from, p_to)
            bundle["comparison"]["results"].append(comparison_result)
        except Exception as exc:  # pragma: no cover - defensive integration handling
            bundle["comparison"]["errors"][compare_tree_id] = _format_step_error(exc)

    if as_json:
        click.echo(json.dumps(bundle, indent=2))
    else:
        click.echo(format_investigation(bundle))
