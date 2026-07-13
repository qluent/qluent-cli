"""Composable query-plan commands: `qluent catalog` and `qluent plan`.

The deterministic sibling of `qluent query`: instead of sending natural
language through the backend's LLM workflow, the caller (typically an agent)
authors a typed QueryPlan against the project's closed-world catalog and the
backend compiles it to SQL. Unknown columns/metrics are rejected with a
repairable message (status ``plan_invalid``) — fix the plan and re-run.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import httpx

from qluent_cli import sessions
from qluent_cli.client import QluentClient
from qluent_cli.config import QluentConfig, load_config
from qluent_cli.formatters import format_query_result
from qluent_cli.output import echo_status
from qluent_cli.plan_contracts import (
    STATUS_OK,
    STATUS_PLAN_INVALID,
    CatalogContract,
    PlanContract,
    build_catalog_contract,
    build_plan_contract,
)
from qluent_cli.rendering import Result, render


def _heartbeat(_stage: str, elapsed: float) -> None:
    echo_status(f"[qluent] awaiting response... ({int(elapsed)}s)")


def _persist_run_safely(**kwargs):
    try:
        return sessions.record_run(**kwargs)
    except Exception as exc:
        click.echo(f"Warning: failed to persist run: {exc}", err=True)
        return None


def _format_catalog(contract: CatalogContract) -> str:
    """Compact human listing of the vocabulary a plan may use."""
    catalog = contract.get("catalog") or {}
    lines: list[str] = []

    bases = catalog.get("bases") or {}
    lines.append(f"bases ({len(bases)}):")
    for name, base in sorted(bases.items()):
        columns = base.get("columns") or []
        lines.append(f"  {name}: {len(columns)} columns")

    metrics = catalog.get("metrics") or {}
    lines.append(f"metrics ({len(metrics)}):")
    for name, metric_bases in sorted(metrics.items()):
        on = f" [{', '.join(metric_bases)}]" if metric_bases else ""
        lines.append(f"  {name}{on}")

    relationships = catalog.get("relationships") or {}
    if relationships:
        lines.append(f"relationships ({len(relationships)}):")
        for name, rel in sorted(relationships.items()):
            lines.append(
                f"  {name}: {rel.get('left_base')} {rel.get('cardinality')} "
                f"{rel.get('right_base')}"
            )

    derived = catalog.get("derived_dimensions") or []
    if derived:
        lines.append(f"derived dimensions: {', '.join(derived)}")

    lines.append("")
    lines.append(
        "Full vocabulary, aliases and the QueryPlan JSON schema: --json-output"
    )
    return "\n".join(lines)


def _format_plan_result(contract: PlanContract, *, show_sql: bool) -> str:
    """Table via the shared query formatter, plus the plan-specific metadata
    an agent (or human) needs before combining results."""
    text = format_query_result(contract, show_sql=show_sql)
    extras: list[str] = []
    grain = contract.get("grain")
    if grain:
        extras.append(f"grain: {', '.join(grain)}")
    metrics = contract.get("metrics") or {}
    non_summable = sorted(
        name for name, info in metrics.items() if not info.get("summable", False)
    )
    if non_summable:
        extras.append(
            f"not summable across results: {', '.join(non_summable)} "
            "(recompute instead of adding)"
        )
    if extras:
        text = f"{text}\n\n" + "\n".join(extras)
    return text


@click.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def catalog(as_json: bool) -> None:
    """Show the project's query catalog — the vocabulary for `qluent plan`.

    Lists the bases, metrics (with the bases that can compute them),
    relationships and derived dimensions a QueryPlan may reference. The JSON
    output additionally carries the QueryPlan JSON schema (`plan_schema`).
    """
    config = load_config()
    client = QluentClient(config)

    try:
        raw = client.get_query_catalog()
    except httpx.HTTPStatusError as exc:
        raise click.ClickException(
            f"API error {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc

    contract = build_catalog_contract(raw, config)
    if contract.get("status") != STATUS_OK:
        code = contract.get("error_code") or "CATALOG_UNAVAILABLE"
        raise click.ClickException(
            f"{code}: {contract.get('error') or 'could not load the query catalog'}"
        )
    render(
        Result(json_payload=contract, human=lambda: _format_catalog(contract)),
        as_json=as_json,
    )


def _load_plan_document(
    plan_json: str | None, plan_file: str | None
) -> dict:
    if bool(plan_json) == bool(plan_file):
        raise click.ClickException(
            "Provide the plan exactly one way: as the PLAN_JSON argument or "
            "via --file."
        )
    text = Path(plan_file).read_text() if plan_file else str(plan_json)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Plan is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise click.ClickException("Plan must be a JSON object (a QueryPlan document).")
    return document


@click.command()
@click.argument("plan_json", required=False)
@click.option(
    "--file",
    "plan_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Read the QueryPlan JSON from a file instead of the argument.",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def plan(plan_json: str | None, plan_file: str | None, as_json: bool) -> None:
    """Compile and run a typed QueryPlan against the project's query catalog.

    PLAN_JSON is a QueryPlan document (see `qluent catalog` for the vocabulary
    and `plan_schema`). Deterministic: the same plan always compiles to the
    same SQL, and the compiler rejects anything outside the catalog. A
    rejected plan renders with status "plan_invalid" and a repairable error
    message — fix the plan and re-run.
    """
    config = load_config()
    client = QluentClient(config)
    document = _load_plan_document(plan_json, plan_file)

    try:
        raw = client.execute_plan(document, progress_callback=_heartbeat)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise click.ClickException(
                "Rate limited by the API — wait a moment and retry."
            ) from exc
        raise click.ClickException(
            f"API error {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc

    contract = build_plan_contract(raw, config)
    status = contract.get("status")
    if status == STATUS_OK:
        record = _persist_run_safely(
            command=sessions.PLAN_COMMAND,
            tree_id=None,
            period_start=None,
            period_end=None,
            comparison_start=None,
            comparison_end=None,
            profile=f"{config.user_email}@{config.api_url}",
            client_safe=config.client_safe,
            args={"plan": document},
            payload=contract,
        )

        def _human() -> str:
            text = _format_plan_result(contract, show_sql=not config.client_safe)
            if record:
                text = f"{text}\n\nrun_id: {record.run_id} (saved)"
            return text

        render(Result(json_payload=contract, human=_human), as_json=as_json)
    elif status == STATUS_PLAN_INVALID:
        # A repairable outcome, not a failure: render the contract (exit 0) so
        # an agent reads the error from stdout, corrects the plan, and re-runs.
        def _human_invalid() -> str:
            return (
                f"Plan rejected ({contract.get('error_code')}): "
                f"{contract.get('error')}\n\nFix the plan and re-run."
            )

        render(Result(json_payload=contract, human=_human_invalid), as_json=as_json)
    else:
        code = contract.get("error_code") or "PLAN_FAILED"
        raise click.ClickException(
            f"{code}: {contract.get('error') or 'plan execution failed'}"
        )
