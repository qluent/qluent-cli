"""Shared helpers for agent-facing output contracts."""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any


def inclusive_day_count(window: dict[str, Any] | None) -> int | None:
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
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "source": source,
        "project_uuid": project_uuid,
        "tree_id": tree_id,
    }
    if node_id is not None:
        data["node_id"] = node_id
    if metric_id is not None:
        data["metric_id"] = metric_id
    return data
