"""Qluent CLI entry point."""

from __future__ import annotations

import click

from qluent_cli.trees import trees


@click.group()
def cli() -> None:
    """Qluent — metric tree analysis from the command line."""


@cli.command()
@click.option("--api-key", help="API key (qk_...)")
@click.option("--url", help="API base URL")
@click.option("--project", help="Project UUID")
@click.option("--email", help="User email")
def config(api_key: str | None, url: str | None, project: str | None, email: str | None) -> None:
    """Configure Qluent API credentials."""
    from qluent_cli.config import save_config

    if not any([api_key, url, project, email]):
        # Show current config
        from qluent_cli.config import CONFIG_FILE

        if CONFIG_FILE.exists():
            click.echo(CONFIG_FILE.read_text())
        else:
            click.echo("No config file found. Run: qluent config --api-key qk_... --project UUID --email you@co.com")
        return

    result = save_config(api_key=api_key, api_url=url, project_uuid=project, user_email=email)
    click.echo(f"Config saved to ~/.qluent/config.json")
    for k, v in result.items():
        display = v[:10] + "..." if k == "api_key" and len(v) > 10 else v
        click.echo(f"  {k}: {display}")


cli.add_command(trees)
