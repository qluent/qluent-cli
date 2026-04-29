"""Claude Code plugin install bootstrap.

Wraps `claude plugin marketplace add` / `install` so `qluent login` can offer a
one-time install of the qluent Claude Code plugin. Plugin lifecycle (updates,
version tracking) is owned by Claude Code's `/plugin marketplace update` flow;
this module deliberately does not check or manage plugin versions.
"""

from __future__ import annotations

import shutil
import subprocess

import click

from qluent_cli.output import echo_status

MARKETPLACE_SOURCE = "qluent/qluent-plugin-cc"
MARKETPLACE_NAME = "qluent-metric-trees"
PLUGIN_ID = f"qluent@{MARKETPLACE_NAME}"


def claude_cli_available() -> bool:
    return shutil.which("claude") is not None


_STEP_TIMEOUT_SECONDS = 180
_LIST_TIMEOUT_SECONDS = 10


def _exec(cmd: list[str], *, timeout: int = _STEP_TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """Run cmd and return (returncode, stdout, stderr).

    Returncode is -1 with the error in stderr when the call timed out or the
    binary was missing.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"
    except OSError as exc:
        return -1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _run(cmd: list[str]) -> tuple[bool, str]:
    rc, stdout, stderr = _exec(cmd)
    if rc == 0:
        return True, ""
    message = (stderr or stdout or "").strip()
    return False, message or f"exit {rc}"


def _run_steps(steps: tuple[list[str], ...]) -> bool:
    for cmd in steps:
        ok, message = _run(cmd)
        if not ok:
            echo_status(f"  Failed: {' '.join(cmd[1:])}")
            if message:
                echo_status(f"  {message}")
            return False
    return True


def _capture(cmd: list[str], *, timeout: int = _LIST_TIMEOUT_SECONDS) -> str | None:
    rc, stdout, _ = _exec(cmd, timeout=timeout)
    if rc != 0:
        return None
    return stdout or ""


def is_claude_plugin_installed() -> bool:
    """Return True if `claude plugin list` mentions the qluent plugin."""
    output = _capture(["claude", "plugin", "list"])
    if output is None:
        return False
    return PLUGIN_ID in output


def install_claude_plugin() -> bool:
    """Add the marketplace and install the plugin.

    Both subcommands are idempotent — they exit 0 with an "already installed"
    message when the marketplace/plugin is already on disk.
    """
    return _run_steps((
        ["claude", "plugin", "marketplace", "add", MARKETPLACE_SOURCE],
        ["claude", "plugin", "install", PLUGIN_ID],
    ))


def _manual_hint() -> str:
    return (
        "Install Claude Code (https://claude.ai/code), then run:\n"
        f"  claude plugin marketplace add {MARKETPLACE_SOURCE}\n"
        f"  claude plugin install {PLUGIN_ID}"
    )


def _refresh_tip() -> str:
    return (
        f"Tip: in Claude Code, run /plugin marketplace update {MARKETPLACE_NAME} "
        "to refresh the qluent plugin."
    )


def offer_claude_plugin_install(install_plugin: bool | None) -> None:
    """Install the qluent Claude Code plugin if it isn't already, or skip.

    install_plugin:
      - True  : install without prompting
      - False : skip silently
      - None  : prompt (default Yes)

    When the plugin is already installed, prints a static refresh tip pointing
    at Claude Code's own `/plugin marketplace update` flow. We do not compare
    versions or trigger updates ourselves.
    """
    if install_plugin is False:
        return

    if not claude_cli_available():
        if install_plugin is True:
            echo_status(_manual_hint())
        else:
            echo_status("Claude Code CLI not detected. " + _manual_hint())
        return

    if is_claude_plugin_installed():
        echo_status(_refresh_tip())
        return

    if install_plugin is None and not click.confirm(
        "Install the qluent plugin in Claude Code?", default=True
    ):
        return
    if install_claude_plugin():
        echo_status(f"Claude Code plugin ready: {PLUGIN_ID}")
