"""Root-cause analysis commands."""

from __future__ import annotations

import json

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import format_root_cause
from qluent_cli.utils import parse_filters, resolve_date_args


@click.group()
def rca() -> None:
    """Deterministic root-cause analysis commands."""


@rca.command()
@click.argument("tree_id")
@click.option("--period", "-p", default=None, help='Period like "last week" or "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--segment-by", "segment_by", multiple=True, help="Dimension to consider for segment RCA (repeatable)")
@click.option("--filter", "filters", multiple=True, help="Filter as dimension=value (repeatable)")
@click.option("--max-depth", default=3, type=click.IntRange(1, 6), help="Maximum tree depth to traverse")
@click.option("--max-branches", default=2, type=click.IntRange(1, 10), help="Maximum child branches to follow per node")
@click.option("--max-segments", default=5, type=click.IntRange(1, 20), help="Maximum segments to show per node")
@click.option(
    "--min-contribution-share",
    default=0.1,
    type=click.FloatRange(0.0, 1.0),
    help="Minimum absolute direct contribution share required to follow a child branch",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def analyze(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    segment_by: tuple[str, ...],
    filters: tuple[str, ...],
    max_depth: int,
    max_branches: int,
    max_segments: int,
    min_contribution_share: float,
    as_json: bool,
) -> None:
    """Run deterministic root-cause analysis for a metric tree."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    parsed_filters = parse_filters(filters)

    client = QluentClient(load_config())
    data = client.root_cause_tree(
        tree_id,
        c_from,
        c_to,
        p_from,
        p_to,
        segment_by=list(segment_by),
        filters=parsed_filters,
        max_depth=max_depth,
        max_branching=max_branches,
        max_segments=max_segments,
        min_contribution_share=min_contribution_share,
    )

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_root_cause(data))
