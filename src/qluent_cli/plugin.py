"""Claude Code plugin auto-install helpers.

Wraps `claude plugin marketplace add` / `install` / `update` so qluent
commands can wire up (or refresh) the Claude Code plugin without the user
having to run the slash commands manually.
"""

from __future__ import annotations

import shutil
import subprocess

import click

MARKETPLACE_SOURCE = "qluent/qluent-plugin-cc"
MARKETPLACE_NAME = "qluent-metric-trees"
PLUGIN_ID = f"qluent@{MARKETPLACE_NAME}"


def claude_cli_available() -> bool:
    return shutil.which("claude") is not None


_STEP_TIMEOUT_SECONDS = 180


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_STEP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {_STEP_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return False, str(exc)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return False, message or f"exit {result.returncode}"
    return True, ""


def _run_steps(steps: tuple[list[str], ...]) -> bool:
    for cmd in steps:
        ok, message = _run(cmd)
        if not ok:
            click.echo(f"  Failed: {' '.join(cmd[1:])}", err=True)
            if message:
                click.echo(f"  {message}", err=True)
            return False
    return True


def install_claude_plugin() -> bool:
    """Add the marketplace and install the plugin.

    Both subcommands are idempotent — they exit 0 with an "already installed"
    message when the marketplace/plugin is already on disk.
    """
    return _run_steps((
        ["claude", "plugin", "marketplace", "add", MARKETPLACE_SOURCE],
        ["claude", "plugin", "install", PLUGIN_ID],
    ))


def update_claude_plugin() -> bool:
    """Refresh the marketplace and pull the latest plugin version.

    Runs `claude plugin marketplace update <name>` then `claude plugin update
    <plugin>`. No-ops cleanly when nothing has changed upstream.
    """
    return _run_steps((
        ["claude", "plugin", "marketplace", "update", MARKETPLACE_NAME],
        ["claude", "plugin", "update", PLUGIN_ID],
    ))


def _manual_hint() -> str:
    return (
        "Install Claude Code (https://claude.ai/code), then run:\n"
        f"  claude plugin marketplace add {MARKETPLACE_SOURCE}\n"
        f"  claude plugin install {PLUGIN_ID}"
    )


def offer_claude_plugin_install(install_plugin: bool | None) -> None:
    """Install (or skip) the qluent Claude Code plugin.

    install_plugin:
      - True  : install without prompting
      - False : skip silently
      - None  : prompt (default Yes)
    """
    if install_plugin is False:
        return

    if not claude_cli_available():
        if install_plugin is True:
            click.echo(_manual_hint())
        else:
            click.echo("Claude Code CLI not detected. " + _manual_hint())
        return

    if install_plugin is None:
        if not click.confirm(
            "Install the qluent plugin in Claude Code?", default=True
        ):
            return

    if install_claude_plugin():
        click.echo(f"Claude Code plugin ready: {PLUGIN_ID}")
