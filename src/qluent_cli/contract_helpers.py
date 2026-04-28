"""Shared types and helpers for agent-facing output contracts.

The TypedDicts here document the **interface** of values that flow between
contract modules and their consumers. They describe the JSON-serialisable
shape that callers (formatters, MCP server, --json-output) can rely on.
"""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any, TypedDict


class Window(TypedDict, total=False):
    date_from: str
    date_to: str
    partial_period: bool
    is_partial: bool


class Provenance(TypedDict, total=False):
    source: str
    project_uuid: str
    tree_id: str
    node_id: str
    metric_id: Any


class WindowMetadata(TypedDict):
    current_day_count: int | None
    comparison_day_count: int | None
    normalized_delta_included: bool
    current_partial_period: bool
    comparison_partial_period: bool
    current_window_zero_or_null: bool
    comparison_window_zero_or_null: bool


class ProjectContext(TypedDict):
    project_uuid: str
    user_email: str | None
    api_url: str
    client_safe: bool


def inclusive_day_count(window: Window | dict[str, Any] | None) -> int | None:
    if not window:
        return None
    try:
        start = dt_date.fromisoformat(str(window["date_from"]))
        end = dt_date.fromisoformat(str(window["date_to"]))
    except (KeyError, ValueError, TypeError):
        return None
    return (end - start).days + 1


def provenance(
    *,
    source: str,
    project_uuid: str,
    tree_id: str,
    node_id: str | None = None,
    metric_id: Any = None,
) -> Provenance:
    data: Provenance = {
        "source": source,
        "project_uuid": project_uuid,
        "tree_id": tree_id,
    }
    if node_id is not None:
        data["node_id"] = node_id
    if metric_id is not None:
        data["metric_id"] = metric_id
    return data
