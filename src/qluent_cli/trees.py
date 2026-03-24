"""Metric tree commands — list, get, evaluate."""

from __future__ import annotations

import json

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import format_evaluation, format_tree_detail, format_tree_list


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

    client = QluentClient(load_config())
    data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_evaluation(data))
