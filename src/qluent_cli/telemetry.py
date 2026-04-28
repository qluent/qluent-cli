"""Lightweight, opt-out usage tracking for the Qluent CLI.

Fires a fire-and-forget POST to ``<api_url>/api/v1/telemetry/cli`` after each
command. All errors are swallowed — telemetry must never affect the user's
command outcome or latency beyond a small bounded wait.

Opt out via ``QLUENT_NO_TELEMETRY=1`` or ``"telemetry_enabled": false`` in
``~/.qluent/config.json``.
"""

from __future__ import annotations

import os
import platform
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from qluent_cli import __version__
from qluent_cli.config import (
    DEFAULT_API_URL,
    _parse_bool,
    load_raw_config,
)

TELEMETRY_PATH = "/api/v1/telemetry/cli"
_FLUSH_TIMEOUT_SEC = 1.0
_REQUEST_TIMEOUT_SEC = 2.0
_GROUP_COMMANDS = {"trees", "rca", "claude", "elasticity", "suggestions", "config"}

_pending_threads: list[threading.Thread] = []


def _is_disabled(raw_config: dict[str, Any]) -> bool:
    if "QLUENT_NO_TELEMETRY" in os.environ:
        return _parse_bool(os.environ["QLUENT_NO_TELEMETRY"])
    if "telemetry_enabled" in raw_config:
        return not _parse_bool(raw_config["telemetry_enabled"])
    return False


def _command_from_argv(argv: list[str]) -> str:
    """Best-effort: extract subcommand path from argv, ignoring flags/values.

    For ``qluent trees evaluate --period last-month foo`` returns
    ``trees evaluate``. For ``qluent --version`` returns ``""``.
    """
    parts: list[str] = []
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            if "=" not in token and token not in {"--help", "--version", "--json-output"}:
                # Conservatively assume the next token is its value; a few false
                # positives here are fine — we only care about leading subcmds.
                skip_next = True
            continue
        parts.append(token)
        if not parts or parts[0] not in _GROUP_COMMANDS:
            break
        if len(parts) >= 2:
            break
    return " ".join(parts)


def _build_payload(
    command: str,
    duration_ms: int,
    exit_code: int,
    error_type: str | None,
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cli_version": __version__,
        "command": command or "(root)",
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "error_type": error_type,
        "platform": sys.platform,
        "python_version": platform.python_version(),
        "project_uuid": raw_config.get("project_uuid") or None,
        "user_email": raw_config.get("user_email") or None,
        "invoked_by": os.environ.get("QLUENT_INVOKED_BY") or "cli",
    }


def _resolve_api_url(raw_config: dict[str, Any]) -> str:
    return str(
        os.environ.get("QLUENT_API_URL")
        or raw_config.get("api_url")
        or DEFAULT_API_URL
    ).rstrip("/")


def _post_silently(url: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
    try:
        httpx.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT_SEC)
    except Exception:
        pass


def track_command(
    *,
    command: str,
    duration_ms: int,
    exit_code: int,
    error_type: str | None = None,
) -> None:
    """Fire-and-forget usage event. Never raises."""
    try:
        raw_config = load_raw_config()
        if _is_disabled(raw_config):
            return
        payload = _build_payload(command, duration_ms, exit_code, error_type, raw_config)
        api_url = _resolve_api_url(raw_config)
        url = f"{api_url}{TELEMETRY_PATH}"
        headers: dict[str, str] = {}
        api_key = os.environ.get("QLUENT_API_KEY") or raw_config.get("api_key")
        if api_key:
            headers["X-API-Key"] = str(api_key)
        thread = threading.Thread(
            target=_post_silently,
            args=(url, payload, headers),
            daemon=True,
        )
        thread.start()
        _pending_threads.append(thread)
    except Exception:
        pass


def flush(timeout: float = _FLUSH_TIMEOUT_SEC) -> None:
    """Wait briefly for any in-flight telemetry threads. Never raises."""
    deadline = time.monotonic() + timeout
    for thread in _pending_threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        try:
            thread.join(timeout=remaining)
        except Exception:
            pass


@contextmanager
def track_lifecycle(argv: list[str]) -> Iterator[None]:
    """Track a CLI invocation, capturing duration and exit code."""
    start = time.monotonic()
    command = _command_from_argv(argv)
    exit_code = 0
    error_type: str | None = None
    try:
        yield
    except SystemExit as exc:
        code = exc.code
        exit_code = code if isinstance(code, int) else (0 if code is None else 1)
        raise
    except BaseException as exc:
        exit_code = 1
        error_type = type(exc).__name__
        raise
    finally:
        try:
            duration_ms = int((time.monotonic() - start) * 1000)
            track_command(
                command=command,
                duration_ms=duration_ms,
                exit_code=exit_code,
                error_type=error_type,
            )
            flush()
        except Exception:
            pass
