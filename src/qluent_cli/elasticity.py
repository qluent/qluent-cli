"""Elasticity analysis command."""

from __future__ import annotations

import json

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.formatters import format_elasticity
from qluent_cli.utils import parse_filters, resolve_date_args


@click.command()
@click.argument("tree_id")
@click.option("--outcome", required=True, help="Outcome metric node id")
@click.option("--lever", required=True, help="Lever metric node id")
@click.option("--dimension", default=None, help="Dimension for segmented elasticity")
@click.option("--period", "-p", default=None, help='Period like "last 12 complete weeks"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--filter", "filters", multiple=True, help="Filter as dimension=value (repeatable)")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def elasticity(
    tree_id: str,
    outcome: str,
    lever: str,
    dimension: str | None,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    filters: tuple[str, ...],
    as_json: bool,
) -> None:
    """Analyze observed elasticity between a lever and an outcome metric."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    parsed_filters = parse_filters(filters)
    config = load_config()
    client = QluentClient(config)
    data = client.elasticity_tree(
        tree_id,
        c_from,
        c_to,
        p_from,
        p_to,
        outcome=outcome,
        lever=lever,
        dimension=dimension,
        filters=parsed_filters,
    )
    data.setdefault("contract_kind", "elasticity_analysis")
    data.setdefault("deterministic", True)
    data.setdefault("tree_id", tree_id)
    data.setdefault("outcome", outcome)
    data.setdefault("lever", lever)
    data.setdefault("dimension", dimension)
    data.setdefault("current_window", {"date_from": c_from, "date_to": c_to})
    data.setdefault("comparison_window", {"date_from": p_from, "date_to": p_to})
    data.setdefault("evidence_type", "observed_correlation")
    data.setdefault("warnings", [])
    data.setdefault(
        "provenance",
        {
            "source": "metric_tree_elasticity",
            "project_uuid": config.project_uuid,
            "tree_id": tree_id,
            "outcome": outcome,
            "lever": lever,
        },
    )

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_elasticity(data))
