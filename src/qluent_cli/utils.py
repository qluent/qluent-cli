"""Shared helpers used by multiple CLI command modules."""

from __future__ import annotations

import json

import click
import httpx


def parse_filters(filter_args: tuple[str, ...]) -> dict[str, list[str]]:
    """Parse dimension=value filter arguments into a grouped dict."""
    filters: dict[str, list[str]] = {}
    for raw_filter in filter_args:
        if "=" not in raw_filter:
            raise click.BadParameter(
                f"Invalid filter '{raw_filter}'. Use dimension=value.",
                param_hint="filter",
            )
        key, value = raw_filter.split("=", 1)
        cleaned_key = key.strip()
        cleaned_value = value.strip()
        if not cleaned_key or not cleaned_value:
            raise click.BadParameter(
                f"Invalid filter '{raw_filter}'. Use dimension=value.",
                param_hint="filter",
            )
        filters.setdefault(cleaned_key, []).append(cleaned_value)
    return filters


def format_step_error(exc: Exception) -> str:
    """Format an exception from an investigation step into a human-readable string."""
    if isinstance(exc, click.ClickException):
        return exc.message

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            raw_detail = payload.get("error") or payload.get("detail") or payload.get("message")
            if isinstance(raw_detail, dict):
                detail = json.dumps(raw_detail, sort_keys=True)
            elif raw_detail is not None:
                detail = str(raw_detail)
        if not detail:
            detail = response.text.strip()
        if detail:
            return f"{response.status_code} {detail}"
        return f"{response.status_code} {exc}"

    return str(exc)


def resolve_date_args(
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
) -> tuple[str, str, str, str]:
    """Resolve date arguments into (c_from, c_to, p_from, p_to) strings."""
    from qluent_cli.dates import infer_windows

    if current_range and compare_range:
        c_from, c_to = current_range.split(":")
        p_from, p_to = compare_range.split(":")
    elif current_range:
        c_from, c_to = current_range.split(":")
        windows = infer_windows(f"{c_from} {c_to}")
        p_from = str(windows.comparison.date_from)
        p_to = str(windows.comparison.date_to)
    else:
        period_text = period or "last 7 days"
        windows = infer_windows(period_text)
        c_from = str(windows.current.date_from)
        c_to = str(windows.current.date_to)
        p_from = str(windows.comparison.date_from)
        p_to = str(windows.comparison.date_to)
    return c_from, c_to, p_from, p_to
