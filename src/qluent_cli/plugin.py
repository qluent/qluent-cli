"""Claude Code plugin install + sync.

Wraps `claude plugin marketplace add` / `install` so `qluent login` can offer a
one-time install of the qluent Claude Code plugin, and `claude plugin
marketplace update` / `claude plugin update` so each subsequent login pulls the
latest published plugin version. Plugin lifecycle is owned by Claude Code's
marketplace flow — this module never inspects, caches, or compares plugin
versions; it just shells out to Claude Code's idempotent commands.
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


def sync_claude_plugin() -> bool:
    """Refresh marketplace metadata and pull the latest plugin version.

    Idempotent — no-ops cleanly when nothing has changed upstream. Run from the
    login path on every successful login so users don't have to remember to
    invoke `/plugin marketplace update` manually (third-party marketplaces
    have auto-update off by default in Claude Code).
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


def _refresh_tip() -> str:
    return (
        f"Tip: in Claude Code, run /plugin marketplace update {MARKETPLACE_NAME} "
        "to refresh the qluent plugin."
    )


def offer_claude_plugin_install(install_plugin: bool | None) -> None:
    """Install or sync the qluent Claude Code plugin.

    install_plugin:
      - True  : install/sync without prompting
      - False : skip silently
      - None  : prompt for install if missing; sync silently if already present

    When the plugin is already installed, runs `sync_claude_plugin()` to pull
    any newer published version. On sync failure, falls back to a static tip
    pointing at Claude Code's own `/plugin marketplace update` flow so the
    user has a recourse without blocking login.
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
        if sync_claude_plugin():
            echo_status(f"Claude Code plugin synced: {PLUGIN_ID}")
        else:
            echo_status(_refresh_tip())
        return

    if install_plugin is None and not click.confirm(
        "Install the qluent plugin in Claude Code?", default=True
    ):
        return
    if install_claude_plugin():
        echo_status(f"Claude Code plugin ready: {PLUGIN_ID}")
