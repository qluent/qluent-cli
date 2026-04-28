"""Claude Code plugin auto-install helpers.

Wraps `claude plugin marketplace add` / `install` / `update` so qluent
commands can wire up (or refresh) the Claude Code plugin without the user
having to run the slash commands manually.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import click

from qluent_cli.output import echo_status

MARKETPLACE_SOURCE = "qluent/qluent-plugin-cc"
MARKETPLACE_NAME = "qluent-metric-trees"
PLUGIN_ID = f"qluent@{MARKETPLACE_NAME}"

# Bumped alongside qluent-plugin-cc releases.
RECOMMENDED_CLAUDE_PLUGIN_VERSION = "0.3.0"


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


def get_installed_claude_plugin_version() -> str | None:
    """Return the installed qluent plugin version, or None if not installed.

    Parses `claude plugin list`, looking for a `qluent@qluent-metric-trees`
    block followed (within a few lines) by a `Version: X.Y.Z` entry.
    """
    output = _capture(["claude", "plugin", "list"])
    if output is None:
        return None
    lines = output.splitlines()
    for idx, line in enumerate(lines):
        if PLUGIN_ID not in line:
            continue
        # Look at the next few lines for a Version: entry.
        for follow in lines[idx : idx + 5]:
            match = re.search(r"Version:\s*([0-9][0-9A-Za-z.\-+]*)", follow)
            if match:
                return match.group(1)
    return None


def _parse_version(value: str) -> tuple[int, ...] | None:
    """Parse a dotted numeric version into a tuple of ints.

    Returns None if the value doesn't start with a numeric component.
    Trailing pre-release/build tags (e.g. "1.2.3-rc1") are ignored.
    """
    head = re.split(r"[-+]", value, maxsplit=1)[0]
    parts = head.split(".")
    try:
        return tuple(int(p) for p in parts if p)
    except ValueError:
        return None


def _is_older(installed: str, recommended: str) -> bool:
    """Return True when `installed` is strictly older than `recommended`."""
    a = _parse_version(installed)
    b = _parse_version(recommended)
    if a is None or b is None:
        return False
    return a < b


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


def _prompt_and_update(installed: str, recommended: str, assume_yes: bool) -> None:
    echo_status("")
    echo_status("Claude Code plugin update available")
    echo_status(f"  Installed:    {PLUGIN_ID} {installed}")
    echo_status(f"  Recommended:  {PLUGIN_ID} {recommended}")

    if not assume_yes and not click.confirm("Update now?", default=True):
        echo_status("Skipped. Run `qluent claude update` to update later.")
        return

    if update_claude_plugin():
        echo_status(f"Claude Code plugin updated to {recommended}: {PLUGIN_ID}")
    else:
        echo_status("Plugin update failed. Run `qluent claude update` to retry.")


def offer_claude_plugin_install(install_plugin: bool | None) -> None:
    """Install, update, or skip the qluent Claude Code plugin.

    install_plugin:
      - True  : install/update without prompting
      - False : skip silently
      - None  : prompt (default Yes)
    """
    if install_plugin is False:
        return

    if not claude_cli_available():
        if install_plugin is True:
            echo_status(_manual_hint())
        else:
            echo_status("Claude Code CLI not detected. " + _manual_hint())
        return

    installed = get_installed_claude_plugin_version()

    if installed is None:
        if install_plugin is None and not click.confirm(
            "Install the qluent plugin in Claude Code?", default=True
        ):
            return
        if install_claude_plugin():
            echo_status(f"Claude Code plugin ready: {PLUGIN_ID}")
        return

    if _is_older(installed, RECOMMENDED_CLAUDE_PLUGIN_VERSION):
        _prompt_and_update(
            installed,
            RECOMMENDED_CLAUDE_PLUGIN_VERSION,
            assume_yes=install_plugin is True,
        )
        return

    echo_status(f"Claude Code plugin up to date: {PLUGIN_ID} {installed}")
