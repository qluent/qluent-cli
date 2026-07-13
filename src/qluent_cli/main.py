"""Qluent CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from qluent_cli import __version__
from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.elasticity import elasticity
from qluent_cli.formatters import format_tree_list
from qluent_cli.plan import catalog, plan
from qluent_cli.query import query
from qluent_cli.rca import rca
from qluent_cli.sessions import KNOWN_COMMANDS
from qluent_cli.suggestions import suggestions
from qluent_cli.trees import trees
from qluent_cli.output import echo_status


@click.group()
@click.option("--quiet", is_flag=True, help="Suppress non-result status output.")
@click.version_option(version=__version__, prog_name="qluent")
@click.pass_context
def cli(ctx: click.Context, quiet: bool) -> None:
    """Qluent — metric tree analysis from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet


def _print_saved_config(data: dict[str, object]) -> None:
    from qluent_cli.config import mask_key

    hidden = {"client_safe", "bearer_token"}
    for key, value in data.items():
        if key in hidden:
            continue
        echo_status(f"  {key}: {mask_key(value) if key == 'api_key' else value}")


def _prompt_required(
    label: str,
    *,
    default: str | None = None,
    show_default: bool = True,
) -> str:
    while True:
        value = click.prompt(
            label,
            default=default or "",
            show_default=show_default and bool(default),
        ).strip()
        if value:
            return value
        echo_status(f"{label} is required")


def _tree_metric_labels(tree: dict[str, Any]) -> list[str]:
    nodes = tree.get("nodes") or []
    return [
        str(node.get("label") or node.get("id"))
        for node in nodes
        if node.get("kind") == "sql_metric" and (node.get("label") or node.get("id"))
    ]


def _build_status_payload() -> dict[str, Any]:
    try:
        config = load_config()
    except SystemExit as exc:
        return {
            "connected": False,
            "error": str(exc),
            "login_command": "qluent login",
        }

    client = QluentClient(config)
    trees_data = client.list_trees()
    normalized_trees = []
    for tree in trees_data.get("trees", []):
        normalized_trees.append(
            {
                "id": tree.get("id"),
                "label": tree.get("label") or tree.get("id"),
                "description": tree.get("description"),
                "metrics": _tree_metric_labels(tree),
            }
        )

    tree_count = len(normalized_trees)
    return {
        "connected": True,
        "project": {
            "uuid": config.project_uuid,
            "api_url": config.api_url,
            "user_email": config.user_email,
            "client_safe": config.client_safe,
        },
        "trees": normalized_trees,
        "capabilities": {
            "query": {
                "available": True,
                "status": "ready",
                "default": True,
            },
            "metric_trees": {
                "available": tree_count > 0,
                "status": "ready" if tree_count else "not_configured",
                "count": tree_count,
                "advanced": True,
            },
        },
        "suggested_first_command": "qluent suggestions --json-output",
    }


def _format_status(payload: dict[str, Any]) -> str:
    if not payload.get("connected"):
        lines = ["Not connected to Qluent"]
        if payload.get("error"):
            lines.extend(["", str(payload["error"])])
        lines.extend(["", "Run: qluent login"])
        return "\n".join(lines)

    project = payload["project"]
    lines = [
        "Connected to Qluent",
        "",
        "Project",
        f"  UUID: {project['uuid']}",
        f"  API: {project['api_url']}",
        f"  User: {project['user_email']}",
        f"  Client safe: {project['client_safe']}",
        "",
        "Capabilities",
        "  Query             ready (default)",
    ]
    tree_count = len(payload.get("trees") or [])
    if tree_count:
        lines.append(f"  Metric trees      {tree_count} available (advanced)")
    else:
        lines.append("  Metric trees      not configured (advanced, optional)")
    lines.extend(["", "Available metric trees"])
    trees_payload = {"trees": payload.get("trees", [])}
    if payload.get("trees"):
        for tree in trees_payload["trees"]:
            metrics = ", ".join(tree.get("metrics") or [])
            detail = f"  {tree['id']}"
            if metrics:
                detail += f"             {metrics}"
            elif tree.get("label"):
                detail += f"             {tree['label']}"
            lines.append(detail)
    else:
        lines.append(format_tree_list(trees_payload))
    lines.extend(["", "Suggested first command", f"  {payload['suggested_first_command']}"])
    return "\n".join(lines)


def _print_status(as_json: bool) -> None:
    payload = _build_status_payload()
    if as_json:
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(_format_status(payload))


@cli.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def status(as_json: bool) -> None:
    """Show the connected project, API environment, and available capabilities."""
    _print_status(as_json)


@cli.command()
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def whoami(as_json: bool) -> None:
    """Alias for status."""
    _print_status(as_json)


@cli.command()
@click.option("--api-key", help="API key (qk_...)")
@click.option("--url", help="API base URL")
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001.",
)
@click.option("--project", help="Project UUID")
@click.option("--email", help="User email")
@click.option(
    "--client-safe/--no-client-safe",
    default=None,
    help="Redact tree formulas and SQL contract details for client-facing use.",
)
@click.option(
    "--bearer-token",
    hidden=True,
    help="Deprecated legacy option. The metric-tree API uses X-API-Key auth.",
)
def config(
    api_key: str | None,
    url: str | None,
    local: bool,
    project: str | None,
    email: str | None,
    client_safe: bool | None,
    bearer_token: str | None,
) -> None:
    """Configure Qluent API credentials."""
    from qluent_cli.config import (
        CONFIG_FILE,
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        load_raw_config,
        save_config,
    )

    if url and local:
        raise click.ClickException("Use either --url or --local, not both.")
    if bearer_token:
        raise click.ClickException(
            "Bearer-token auth is not supported by the metric-tree API. Configure an API key instead."
        )

    effective_url = LOCAL_API_URL if local else url

    if not any([api_key, effective_url, project, email, client_safe is not None]):
        if CONFIG_FILE.exists():
            data = load_raw_config()
            if "client_safe" not in data:
                data["client_safe"] = default_client_safe(
                    str(data.get("api_url") or DEFAULT_API_URL)
                )
            _print_saved_config(data)
        else:
            echo_status("No config file found. Run: qluent setup")
        return

    result = save_config(
        api_key=api_key,
        api_url=effective_url,
        project_uuid=project,
        user_email=email,
        client_safe=client_safe,
    )
    if "client_safe" not in result:
        result["client_safe"] = default_client_safe(
            str(result.get("api_url") or DEFAULT_API_URL)
        )
    echo_status(CONFIG_SAVED_MSG)
    _print_saved_config(result)


CLAUDE_POINTER_BODY = (
    "@AGENTS.md\n"
    "\n"
    "# Claude Code\n"
    "\n"
    "This file imports the shared qluent CLI usage guide from AGENTS.md.\n"
)


def _agent_file_content(kind: str) -> str:
    if kind == "claude-pointer":
        return CLAUDE_POINTER_BODY
    return _load_agent_instructions().strip() + "\n"


def _write_agent_file(path: Path, *, force: bool, kind: str = "agents") -> str:
    content = _agent_file_content(kind)
    if path.exists():
        existing = path.read_text()
        if existing == content:
            return f"{path} is already up to date"
        if not force:
            raise click.ClickException(
                f"{path} already exists. Re-run with --force to overwrite it."
            )
    path.write_text(content)
    return f"Wrote {path}"


def _confirm_and_write_agent_file(
    target: Path, *, force: bool, kind: str = "agents"
) -> None:
    """Prompt to overwrite if needed, then write the agent instructions file."""
    if target.exists() and not force:
        if not click.confirm(f"{target} already exists. Overwrite it?", default=False):
            echo_status(f"Skipped {target.name} generation")
            return
    echo_status(_write_agent_file(target, force=force or target.exists(), kind=kind))


@cli.command()
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001 and local UI at http://localhost:5173.",
)
@click.option(
    "--install-plugin/--no-install-plugin",
    "install_plugin",
    default=None,
    help="Install the qluent Claude Code plugin without prompting (or skip the prompt).",
)
def login(local: bool, install_plugin: bool | None) -> None:
    """Log in via browser (opens qluent-ui for SSO authentication)."""
    from qluent_cli.auth import browser_login
    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        save_config,
    )
    from qluent_cli.plugin import offer_claude_plugin_install

    api_url = LOCAL_API_URL if local else DEFAULT_API_URL

    result = browser_login(api_url)

    if not result.success:
        raise click.ClickException(f"Login failed: {result.error}")

    client_safe = default_client_safe(api_url)
    save_config(
        api_key=result.api_key,
        api_url=api_url,
        project_uuid=result.project_uuid,
        user_email=result.user_email,
        client_safe=client_safe,
    )

    echo_status("Logged in successfully!")
    echo_status(f"  Project: {result.project_uuid}")
    echo_status(f"  Email:   {result.user_email}")
    echo_status(CONFIG_SAVED_MSG)

    _confirm_and_write_agent_file(Path("AGENTS.md"), force=False)
    offer_claude_plugin_install(install_plugin)


@cli.command()
@click.option(
    "--path",
    "agents_path",
    default="AGENTS.md",
    show_default=True,
    help="Where to write the agent instructions file.",
)
@click.option(
    "--claude-path",
    "claude_path",
    hidden=True,
    help="Deprecated alias for --path.",
)
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001.",
)
@click.option(
    "--force", is_flag=True, help="Overwrite an existing instructions file without prompting."
)
@click.option(
    "--install-plugin/--no-install-plugin",
    "install_plugin",
    default=None,
    help="Install the qluent Claude Code plugin without prompting (or skip the prompt).",
)
def setup(
    agents_path: str,
    claude_path: str | None,
    local: bool,
    force: bool,
    install_plugin: bool | None,
) -> None:
    """Interactive first-run setup for client installations."""
    echo_status("Tip: Use 'qluent login' for browser-based login (recommended).\n")

    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        load_raw_config,
        save_config,
    )
    from qluent_cli.plugin import offer_claude_plugin_install

    existing = load_raw_config()

    api_key = _prompt_required(
        "API key",
        default=str(existing.get("api_key") or ""),
        show_default=False,
    )
    project_uuid = _prompt_required(
        "Project UUID",
        default=str(existing.get("project_uuid") or ""),
        show_default=False,
    )
    user_email = _prompt_required(
        "User email",
        default=str(existing.get("user_email") or ""),
        show_default=False,
    )
    api_url = LOCAL_API_URL if local else str(existing.get("api_url") or DEFAULT_API_URL)
    client_safe = default_client_safe(api_url)

    result = save_config(
        api_key=api_key,
        api_url=api_url,
        project_uuid=project_uuid,
        user_email=user_email,
        client_safe=client_safe,
    )
    echo_status(CONFIG_SAVED_MSG)
    _print_saved_config(result)

    target = Path(claude_path or agents_path)
    write_agents = click.confirm(
        f"Write {target}?",
        default=True,
    )
    if write_agents:
        _confirm_and_write_agent_file(target, force=force)
    else:
        echo_status(f"Skipped {target.name} generation")

    offer_claude_plugin_install(install_plugin)


cli.add_command(trees)
cli.add_command(query)
cli.add_command(catalog)
cli.add_command(plan)
cli.add_command(rca)
cli.add_command(elasticity)
cli.add_command(suggestions)

INSTRUCTIONS_FILENAME = "agent_instructions.md"


def _load_agent_instructions() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return (base / INSTRUCTIONS_FILENAME).read_text()


@cli.command()
def instructions() -> None:
    """Print the bundled AGENTS.md snippet for agent integrations."""
    click.echo(_load_agent_instructions())


def _agents_init_impl(*, as_kind: str, target_path: str | None, force: bool) -> None:
    if as_kind == "agents":
        path = Path(target_path or "AGENTS.md")
        echo_status(_write_agent_file(path, force=force, kind="agents"))
        return

    if as_kind == "claude":
        path = Path(target_path or "CLAUDE.md")
        echo_status(_write_agent_file(path, force=force, kind="agents"))
        return

    if as_kind == "both":
        if target_path:
            raise click.ClickException(
                "--path is incompatible with --as both. Run twice with --as agents and "
                "--as claude if you need custom paths."
            )
        echo_status(_write_agent_file(Path("AGENTS.md"), force=force, kind="agents"))
        echo_status(
            _write_agent_file(Path("CLAUDE.md"), force=force, kind="claude-pointer")
        )
        return

    raise click.ClickException(
        f"Unknown --as value: {as_kind}. Use one of: agents, claude, both."
    )


@cli.group()
def agents() -> None:
    """Agent integration helpers (AGENTS.md, CLAUDE.md, ...)."""


@agents.command("init")
@click.option(
    "--as",
    "as_kind",
    type=click.Choice(["agents", "claude", "both"]),
    default="agents",
    show_default=True,
    help=(
        "Which file flavor to write. 'agents' = AGENTS.md, 'claude' = CLAUDE.md "
        "with the same content, 'both' = AGENTS.md plus a tiny CLAUDE.md pointer."
    ),
)
@click.option(
    "--path",
    "target_path",
    default=None,
    help="Where to write the file (defaults: AGENTS.md or CLAUDE.md depending on --as).",
)
@click.option("--force", is_flag=True, help="Overwrite an existing file without prompting.")
def agents_init(as_kind: str, target_path: str | None, force: bool) -> None:
    """Write an agent instructions file (AGENTS.md by default)."""
    _agents_init_impl(as_kind=as_kind, target_path=target_path, force=force)


cli.add_command(agents)


@cli.group()
def claude() -> None:
    """Claude Code integration helpers."""


@claude.command("init")
@click.option(
    "--path",
    "target_path",
    default="CLAUDE.md",
    show_default=True,
    help="Path to write CLAUDE.md",
)
@click.option("--force", is_flag=True, help="Overwrite an existing CLAUDE.md")
def claude_init(target_path: str, force: bool) -> None:
    """Alias for `qluent agents init --as claude` (writes CLAUDE.md)."""
    _agents_init_impl(as_kind="claude", target_path=target_path, force=force)


cli.add_command(claude)


@cli.group()
def mcp() -> None:
    """Model Context Protocol integration for non-Claude agents."""


@mcp.command("serve")
def mcp_serve() -> None:
    """Run an MCP stdio server that exposes the qluent client as MCP tools."""
    try:
        from qluent_cli.mcp_server import serve_stdio
    except ImportError as exc:
        raise click.ClickException(
            "The 'mcp' Python SDK is not installed. Install it with: pip install mcp"
        ) from exc

    import asyncio

    asyncio.run(serve_stdio())


cli.add_command(mcp)


@cli.group()
def runs() -> None:
    """Inspect, replay, and prune persisted investigate / deep-dive runs."""


def _format_runs_table(records: list[Any]) -> str:
    if not records:
        return "No persisted runs."
    rows = [("RUN_ID", "STARTED", "COMMAND", "TREE", "PERIOD")]
    for r in records:
        period = "-"
        if r.period_start and r.period_end:
            period = f"{r.period_start}..{r.period_end}"
        rows.append(
            (
                r.run_id,
                r.started_at,
                r.command,
                r.tree_id or "*",
                period,
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(value.ljust(widths[i]) for i, value in enumerate(row))
        for row in rows
    )


@runs.command("list")
@click.option("--tree", "tree_id", default=None, help="Filter to a specific tree id.")
@click.option(
    "--command",
    "command_filter",
    default=None,
    type=click.Choice(KNOWN_COMMANDS),
    help="Filter by command kind.",
)
@click.option(
    "--since",
    default=None,
    help="Only runs started within this duration (e.g. '7d', '30d', '7 days ago').",
)
@click.option("--limit", default=None, type=click.IntRange(1, 1000), help="Cap the result count.")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def runs_list(
    tree_id: str | None,
    command_filter: str | None,
    since: str | None,
    limit: int | None,
    as_json: bool,
) -> None:
    """List persisted runs newest-first."""
    from qluent_cli import sessions

    try:
        records = sessions.list_runs(
            tree_id=tree_id,
            command=command_filter,
            since=since,
            limit=limit,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if as_json:
        payload = [
            {
                "run_id": r.run_id,
                "command": r.command,
                "tree_id": r.tree_id,
                "period_start": r.period_start,
                "period_end": r.period_end,
                "comparison_start": r.comparison_start,
                "comparison_end": r.comparison_end,
                "started_at": r.started_at,
                "profile": r.profile,
                "client_safe": r.client_safe,
                "path": str(r.path),
            }
            for r in records
        ]
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(_format_runs_table(records))


@runs.command("show")
@click.argument("run_id", required=False)
@click.option("--last", "use_last", is_flag=True, help="Show the most recent matching run.")
@click.option("--tree", "tree_id", default=None, help="When used with --last, filter to a tree id.")
@click.option(
    "--command",
    "command_filter",
    default=None,
    type=click.Choice(KNOWN_COMMANDS),
    help="When used with --last, filter by command kind.",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def runs_show(
    run_id: str | None,
    use_last: bool,
    tree_id: str | None,
    command_filter: str | None,
    as_json: bool,
) -> None:
    """Print the stored result for a run."""
    from qluent_cli import sessions

    if not run_id and not use_last:
        raise click.ClickException("Provide a RUN_ID or use --last.")
    if run_id and use_last:
        raise click.ClickException("Use either RUN_ID or --last, not both.")

    if use_last:
        record = sessions.find_last_run(command=command_filter, tree_id=tree_id)
        if record is None:
            raise click.ClickException("No persisted runs match.")
    else:
        record = sessions.get_run(run_id)
        if record is None:
            raise click.ClickException(f"No run found for run_id={run_id}")

    payload = record.load()
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"run_id: {record.run_id}")
    click.echo(f"command: {record.command}")
    if record.tree_id:
        click.echo(f"tree: {record.tree_id}")
    if record.period_start and record.period_end:
        click.echo(f"period: {record.period_start}..{record.period_end}")
    click.echo(f"started: {record.started_at}")
    click.echo(f"path: {record.path}")
    click.echo("")
    click.echo(json.dumps(payload.get("result"), indent=2))


@runs.command("prune")
@click.option("--older-than", default=None, help="Remove runs older than this duration (e.g. '30d').")
@click.option("--max", "max_runs", default=None, type=click.IntRange(0, 100000), help="Keep at most N most-recent runs.")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def runs_prune(older_than: str | None, max_runs: int | None, as_json: bool) -> None:
    """Delete old runs by age and/or beyond a most-recent cap."""
    from qluent_cli import sessions

    if older_than is None and max_runs is None:
        raise click.ClickException("Provide --older-than and/or --max.")

    try:
        removed = sessions.prune_runs(older_than=older_than, max_runs=max_runs)
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if as_json:
        click.echo(json.dumps({"removed": [r.run_id for r in removed]}, indent=2))
        return
    click.echo(f"Removed {len(removed)} run(s).")


cli.add_command(runs)


if __name__ == "__main__":
    cli()
