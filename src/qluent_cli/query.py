"""Ad-hoc natural-language query command.

Unlike the metric-tree commands, `qluent query` drives the backend's LLM
workflow engine (NL -> SQL -> execution -> results). It streams SSE progress
by default so multi-minute runs show stage updates; `--sync` uses the plain
POST endpoint. Results are non-deterministic — the JSON contract marks them
as such.
"""

from __future__ import annotations

import click
import httpx

from qluent_cli import sessions
from qluent_cli.client import QluentClient, QueryStreamUnsupported
from qluent_cli.config import QluentConfig, load_config
from qluent_cli.formatters import format_query_clarification, format_query_result
from qluent_cli.output import echo_status
from qluent_cli.query_contracts import (
    STATUS_CLARIFICATION,
    STATUS_OK,
    QueryContract,
    build_query_contract,
)
from qluent_cli.rendering import Result, render


def _persist_run_safely(**kwargs):
    try:
        return sessions.record_run(**kwargs)
    except Exception as exc:
        click.echo(f"Warning: failed to persist run: {exc}", err=True)
        return None


def _heartbeat(_stage: str, elapsed: float) -> None:
    echo_status(f"[qluent] awaiting response... ({int(elapsed)}s)")


def _run_streaming(
    client: QluentClient,
    config: QluentConfig,
    question: str,
    thread_id: str | None,
) -> QueryContract:
    sql: str | None = None
    terminal: tuple[str, dict] | None = None
    thread_seen: str | None = None
    try:
        for event, payload in client.iter_query_events(question, thread_id=thread_id):
            if event == "status":
                message = payload.get("message")
                if message:
                    echo_status(f"[qluent] {message}")
                thread_seen = payload.get("thread_id") or thread_seen
            elif event == "sql":
                sql = payload.get("sql")
            elif event in ("result", "clarification", "error"):
                terminal = (event, payload)
                break
    except (httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
        hint = f" on thread {thread_seen}" if thread_seen else ""
        raise click.ClickException(
            f"Stream interrupted ({type(exc).__name__}). The query may still "
            f"complete server-side — re-run to retry{hint}."
        ) from exc

    if terminal is None:
        raise click.ClickException("Stream ended without a result — re-run to retry.")
    event, payload = terminal
    return build_query_contract(payload, config, event=event, sql=sql)


@click.command()
@click.argument("question")
@click.option(
    "--thread",
    "thread_id",
    default=None,
    help="Thread id from a previous query — continues that conversation "
    "(also used to answer clarification questions).",
)
@click.option(
    "--sync",
    "use_sync",
    is_flag=True,
    help="Use the synchronous endpoint instead of streaming progress.",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def query(question: str, thread_id: str | None, use_sync: bool, as_json: bool) -> None:
    """Ask an ad-hoc natural-language question against your data.

    Runs the backend's LLM query workflow (NL -> SQL -> execution). Use this
    for row-level or arbitrary questions the metric trees don't cover; it is
    non-deterministic and can take minutes. Follow up (or answer a
    clarification) by re-running with --thread <thread_id>.
    """
    config = load_config()
    client = QluentClient(config)

    try:
        if use_sync:
            raw = client.query(question, thread_id=thread_id, progress_callback=_heartbeat)
            contract = build_query_contract(raw, config)
        else:
            try:
                contract = _run_streaming(client, config, question, thread_id)
            except QueryStreamUnsupported:
                echo_status(
                    "[qluent] backend does not support streaming; using sync endpoint"
                )
                raw = client.query(
                    question, thread_id=thread_id, progress_callback=_heartbeat
                )
                contract = build_query_contract(raw, config)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise click.ClickException(
                "Rate limited by the API — wait a moment and retry."
            ) from exc
        raise click.ClickException(
            f"API error {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc

    status = contract.get("status")
    if status == STATUS_OK:
        record = _persist_run_safely(
            command=sessions.QUERY_COMMAND,
            tree_id=None,
            period_start=None,
            period_end=None,
            comparison_start=None,
            comparison_end=None,
            profile=f"{config.user_email}@{config.api_url}",
            client_safe=config.client_safe,
            args={"question": question, "thread": thread_id, "sync": use_sync},
            payload=contract,
        )

        def _human() -> str:
            text = format_query_result(contract, show_sql=not config.client_safe)
            if record:
                text = f"{text}\n\nrun_id: {record.run_id} (saved)"
            return text

        render(Result(json_payload=contract, human=_human), as_json=as_json)
    elif status == STATUS_CLARIFICATION:
        render(
            Result(
                json_payload=contract,
                human=lambda: format_query_clarification(contract),
            ),
            as_json=as_json,
        )
    else:
        code = contract.get("error_code") or "QUERY_FAILED"
        raise click.ClickException(f"{code}: {contract.get('error') or 'query failed'}")
