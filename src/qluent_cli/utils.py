"""Shared helpers used by multiple CLI command modules."""

from __future__ import annotations

import click


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
