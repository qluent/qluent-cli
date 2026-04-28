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
