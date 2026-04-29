"""Rendering seam for command output.

Every command branches on `--json-output` to emit either a JSON dump or a
human-formatted string.  Doing this inline at every site means cross-cutting
concerns (indent style, redaction, stderr routing) are re-applied at each
command.  This module owns the branch.

Usage:

    from qluent_cli.rendering import Result, render

    result = Result(json_payload=data, human=lambda: format_evaluation(data))
    render(result, as_json=ctx.obj["as_json"])

Or, when the JSON payload is just the source data:

    result = simple_result(data, formatter=format_evaluation)
    render(result, as_json=...)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import click


HumanRenderer = str | Callable[[], str]


@dataclass(frozen=True)
class Result:
    """A rendered command result.

    `json_payload` is what we emit when `--json-output` is set.  `human`
    is either a pre-formatted string or a zero-arg callable that produces
    one (lazy: never invoked when JSON output is requested).
    """

    json_payload: Any
    human: HumanRenderer


def simple_result(data: Any, *, formatter: Callable[[Any], str]) -> Result:
    """Convenience factory: same `data` for both branches."""
    return Result(json_payload=data, human=lambda: formatter(data))


def render(result: Result, *, as_json: bool | None = None) -> None:
    """Emit the result on stdout.

    `as_json` may be omitted; when omitted, the renderer reads it from the
    Click context's `obj["as_json"]`, set by top-level `--json-output`.
    """
    if as_json is None:
        as_json = _as_json_from_context()
    if as_json:
        click.echo(json.dumps(result.json_payload, indent=2))
    else:
        click.echo(_resolve_human(result.human))


def _resolve_human(human: HumanRenderer) -> str:
    return human() if callable(human) else human


def _as_json_from_context() -> bool:
    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        if isinstance(ctx.obj, dict) and "as_json" in ctx.obj:
            return bool(ctx.obj["as_json"])
        ctx = ctx.parent
    return False
