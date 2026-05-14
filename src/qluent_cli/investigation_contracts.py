"""Typed response contract for metric-tree investigation bundles."""

from __future__ import annotations

from typing import Any, TypedDict

from qluent_cli.contract_helpers import Window


class InvestigationBundle(TypedDict, total=False):
    """Wire response returned by the metric-tree investigate endpoint.

    The backend may persist investigations and return ``analysis_run_uuid``.
    Older backend versions omit it, so every field remains optional.
    """

    analysis_run_uuid: str
    tree_id: str
    tree_label: str
    period_label: str
    current_window: Window | None
    comparison_window: Window | None
    segment_by_used: list[str]
    filters: dict[str, list[str]]
    validation: dict[str, Any]
    trend: dict[str, Any]
    evaluation: dict[str, Any]
    levers: dict[str, Any]
    root_cause: dict[str, Any]
    comparison: dict[str, Any]
    agent: dict[str, Any]
    step_errors: dict[str, Any]
