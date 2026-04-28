"""Output helpers for stdout/stderr discipline."""

from __future__ import annotations

from typing import Any

import click


def is_quiet() -> bool:
    """Return whether non-result chatter should be suppressed."""
    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        if isinstance(ctx.obj, dict) and ctx.obj.get("quiet"):
            return True
        ctx = ctx.parent
    return False


def echo_status(message: Any = "", **kwargs: Any) -> None:
    """Emit a status message to stderr unless quiet mode is active."""
    if is_quiet():
        return
    click.echo(message, err=True, **kwargs)
