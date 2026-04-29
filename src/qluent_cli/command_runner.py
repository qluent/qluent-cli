"""Command-runner decorator — capstone of the architecture refactor.

After the prior deepenings (rendering, window resolver, client configs,
RunManager), every Click command has the same skeleton:

    config = load_config()
    client = QluentClient(config)
    try:
        ... business logic ...
    except PeriodResolutionError as exc:
        raise click.ClickException(str(exc)) from exc
    render(result, as_json=as_json)

`@qluent_command` collapses that.  The wrapped function takes
`(client, config, *args, **kwargs)` and returns a `Result | None`.
"""

from __future__ import annotations

import functools
import sys
from typing import Any, Callable

import click

from qluent_cli.client import QluentClient
from qluent_cli.config import load_config
from qluent_cli.rendering import Result, render
from qluent_cli.window_resolver import PeriodResolutionError


def qluent_command(func: Callable[..., Result | None]) -> Callable[..., Any]:
    """Wrap a Click command body so it receives `client`, `config`, and
    only has to return a `Result` (or `None`) for the renderer to emit.

    The decorator:
      * loads the config and constructs a client
      * forwards Click options/arguments unchanged
      * maps `PeriodResolutionError` to `click.ClickException`
      * renders any returned `Result` with the right `as_json` flag
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        # Resolve load_config / QluentClient via the wrapped function's
        # module first, so existing monkey-patches like
        # `monkeypatch.setattr("qluent_cli.trees.load_config", ...)`
        # continue to work.
        host = sys.modules.get(func.__module__)
        local_load_config = getattr(host, "load_config", load_config)
        local_client_cls = getattr(host, "QluentClient", QluentClient)

        config = local_load_config()
        client = local_client_cls(config)
        try:
            result = func(client, config, *args, **kwargs)
        except PeriodResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        if result is None:
            return
        as_json = bool(kwargs.get("as_json", False))
        render(result, as_json=as_json)

    return wrapper
