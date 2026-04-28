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
from qluent_cli.rca import rca
from qluent_cli.suggestions import suggestions
from qluent_cli.trees import trees


@click.group()
@click.version_option(version=__version__, prog_name="qluent")
def cli() -> None:
    """Qluent — metric tree analysis from the command line."""


def _print_saved_config(data: dict[str, object]) -> None:
    from qluent_cli.config import mask_key

    hidden = {"client_safe", "bearer_token"}
    for key, value in data.items():
        if key in hidden:
            continue
        click.echo(f"  {key}: {mask_key(value) if key == 'api_key' else value}")


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
        click.echo(f"{label} is required")


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

    first_tree = normalized_trees[0]["id"] if normalized_trees else "<tree_id>"
    return {
        "connected": True,
        "project": {
            "uuid": config.project_uuid,
            "api_url": config.api_url,
            "user_email": config.user_email,
            "client_safe": config.client_safe,
        },
        "trees": normalized_trees,
        "suggested_first_command": (
            f'qluent trees investigate {first_tree} --period "last month" --json-output'
        ),
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
        "Available trees",
    ]
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
    """Show the connected project, API environment, user, and available trees."""
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
            click.echo("No config file found. Run: qluent setup")
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
    click.echo(CONFIG_SAVED_MSG)
    _print_saved_config(result)


def _write_claude_file(path: Path, *, force: bool) -> str:
    content = _load_claude_instructions().strip() + "\n"
    if path.exists():
        existing = path.read_text()
        if existing == content:
            return f"{path} is already up to date"
        if not force:
            raise click.ClickException(f"{path} already exists. Re-run with --force to overwrite it.")
    path.write_text(content)
    return f"Wrote {path}"


def _confirm_and_write_claude_file(target: Path, *, force: bool) -> None:
    """Prompt to overwrite if needed, then write CLAUDE.md."""
    if target.exists() and not force:
        if not click.confirm(f"{target} already exists. Overwrite it?", default=False):
            click.echo("Skipped CLAUDE.md generation")
            return
    click.echo(_write_claude_file(target, force=force or target.exists()))


@cli.command()
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001 and local UI at http://localhost:5173.",
)
def login(local: bool) -> None:
    """Log in via browser (opens qluent-ui for SSO authentication)."""
    from qluent_cli.auth import browser_login
    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        save_config,
    )

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

    click.echo("Logged in successfully!")
    click.echo(f"  Project: {result.project_uuid}")
    click.echo(f"  Email:   {result.user_email}")
    click.echo(CONFIG_SAVED_MSG)

    _confirm_and_write_claude_file(Path("CLAUDE.md"), force=False)


@cli.command()
@click.option(
    "--claude-path",
    default="CLAUDE.md",
    show_default=True,
    help="Where to write the Claude Code instructions file.",
)
@click.option(
    "--local",
    is_flag=True,
    help="Use the local API at http://localhost:8001.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing CLAUDE.md without prompting.")
def setup(claude_path: str, local: bool, force: bool) -> None:
    """Interactive first-run setup for client installations."""
    click.echo("Tip: Use 'qluent login' for browser-based login (recommended).\n")

    from qluent_cli.config import (
        CONFIG_SAVED_MSG,
        DEFAULT_API_URL,
        LOCAL_API_URL,
        default_client_safe,
        load_raw_config,
        save_config,
    )

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
    click.echo(CONFIG_SAVED_MSG)
    _print_saved_config(result)

    target = Path(claude_path)
    write_claude = click.confirm(
        f"Write Claude Code instructions to {target}?",
        default=True,
    )
    if not write_claude:
        click.echo("Skipped CLAUDE.md generation")
        return

    _confirm_and_write_claude_file(target, force=force)


cli.add_command(trees)
cli.add_command(rca)
cli.add_command(elasticity)
cli.add_command(suggestions)

INSTRUCTIONS_FILENAME = "claude_instructions.md"


def _load_claude_instructions() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return (base / INSTRUCTIONS_FILENAME).read_text()


@cli.command()
def instructions() -> None:
    """Print a CLAUDE.md snippet for Claude Code integration."""
    click.echo(_load_claude_instructions())


@cli.group()
def claude() -> None:
    """Claude Code integration helpers."""


@claude.command("init")
@click.option("--path", "target_path", default="CLAUDE.md", show_default=True, help="Path to write CLAUDE.md")
@click.option("--force", is_flag=True, help="Overwrite an existing CLAUDE.md")
def claude_init(target_path: str, force: bool) -> None:
    """Write a CLAUDE.md file for Claude Code."""
    click.echo(_write_claude_file(Path(target_path), force=force))


cli.add_command(claude)

if __name__ == "__main__":
    cli()
