"""Elasticity analysis command and the underlying business seam."""

from __future__ import annotations

from typing import Any

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import QluentConfig, load_config
from qluent_cli.formatters import format_elasticity
from qluent_cli.rendering import render, simple_result
from qluent_cli.utils import parse_filters
from qluent_cli.window_resolver import PeriodResolutionError, resolve_period


def analyze_elasticity(
    client: QluentClient,
    config: QluentConfig,
    *,
    tree_id: str,
    outcome: str,
    lever: str,
    current_from: str,
    current_to: str,
    comparison_from: str,
    comparison_to: str,
    dimension: str | None = None,
    filters: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Run elasticity analysis and stamp the deterministic contract fields.

    This is the business seam under the `qluent elasticity` CLI command and
    the `qluent_elasticity` MCP tool. Both adapters call into here so they
    cannot drift on contract shape, defaults, or provenance.
    """
    data = client.elasticity_tree(
        tree_id,
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        outcome=outcome,
        lever=lever,
        dimension=dimension,
        filters=filters or {},
    )
    data.setdefault("contract_kind", "elasticity_analysis")
    data.setdefault("deterministic", True)
    data.setdefault("tree_id", tree_id)
    data.setdefault("outcome", outcome)
    data.setdefault("lever", lever)
    data.setdefault("dimension", dimension)
    data.setdefault("current_window", {"date_from": current_from, "date_to": current_to})
    data.setdefault("comparison_window", {"date_from": comparison_from, "date_to": comparison_to})
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
    return data


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
    try:
        rp = resolve_period(
            period=period,
            current_range=current_range,
            compare_range=compare_range,
        )
    except PeriodResolutionError as exc:
        raise click.ClickException(str(exc)) from exc
    c_from, c_to, p_from, p_to = rp.windows.iso_tuple()
    config = load_config()
    client = QluentClient(config)
    data = analyze_elasticity(
        client,
        config,
        tree_id=tree_id,
        outcome=outcome,
        lever=lever,
        dimension=dimension,
        current_from=c_from,
        current_to=c_to,
        comparison_from=p_from,
        comparison_to=p_to,
        filters=parse_filters(filters),
    )

    render(simple_result(data, formatter=format_elasticity), as_json=as_json)
