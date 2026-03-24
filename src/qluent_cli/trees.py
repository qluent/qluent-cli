"""Metric tree commands — list, get, evaluate, trend, compare."""

from __future__ import annotations

import json

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import (
    format_comparison,
    format_evaluation,
    format_period_label,
    format_trend,
    format_tree_detail,
    format_tree_list,
    format_tree_validation,
)


@click.group()
def trees() -> None:
    """Metric tree commands."""


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
    """Evaluate a metric tree over date windows.

    Examples:

      qluent trees evaluate revenue --period "last week"

      qluent trees evaluate revenue --current 2025-03-10:2025-03-16 --compare 2025-03-03:2025-03-09
    """
    c_from, c_to, p_from, p_to = _resolve_date_args(period, current_range, compare_range)
    client = QluentClient(load_config())
    data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_evaluation(data))


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


@trees.command()
@click.argument("tree_id")
@click.option("--periods", "-n", default=4, type=click.IntRange(1, 52), help="Number of consecutive periods (default: 4)")
@click.option("--grain", "-g", default="week", type=click.Choice(["week", "month"]), help="Period granularity")
@click.option("--as-of", "as_of", default=None, help="Reference date as YYYY-MM-DD (default: today)")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def trend(tree_id: str, periods: int, grain: str, as_of: str | None, as_json: bool) -> None:
    """Show multi-period trend for a metric tree.

    Examples:

      qluent trees trend revenue --periods 4 --grain week

      qluent trees trend net_revenue --periods 3 --grain month

      qluent trees trend revenue --periods 4 --as-of 2025-03-17
    """
    from datetime import date as dt_date

    from qluent_cli.dates import generate_consecutive_windows

    client = QluentClient(load_config())
    ref_date = dt_date.fromisoformat(as_of) if as_of else None

    window_pairs = generate_consecutive_windows(periods, grain, today=ref_date)
    evaluations = []
    for wp in window_pairs:
        data = client.evaluate_tree(
            tree_id,
            str(wp.current.date_from),
            str(wp.current.date_to),
            str(wp.comparison.date_from),
            str(wp.comparison.date_to),
        )
        evaluations.append(data)

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
    """Compare multiple metric trees side by side for the same period.

    Examples:

      qluent trees compare revenue order_volume --period "last week"

      qluent trees compare revenue net_revenue order_volume --current 2025-03-10:2025-03-16 --compare 2025-03-03:2025-03-09
    """
    c_from, c_to, p_from, p_to = _resolve_date_args(period, current_range, compare_range)

    config = load_config()
    client = QluentClient(config)

    results: list[tuple[str, dict]] = []
    for tid in tree_ids:
        data = client.evaluate_tree(tid, c_from, c_to, p_from, p_to)
        results.append((data.get("tree_label", tid), data))

    if as_json:
        click.echo(json.dumps([d for _, d in results], indent=2))
    else:
        click.echo(format_comparison(results, format_period_label(c_from, c_to, p_from, p_to)))
