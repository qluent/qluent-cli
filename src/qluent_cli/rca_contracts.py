"""Stable JSON enrichment for deterministic RCA outputs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TypedDict

from qluent_cli.config import QluentConfig
from qluent_cli.contract_helpers import (
    Provenance,
    Window,
    WindowMetadata,
    inclusive_day_count,
    provenance,
)


RCA_SCHEMA_VERSION = "qluent.rca.v1"


class RCAOutput(TypedDict, total=False):
    """Agent-facing RCA output. Total=False because the upstream API response
    forms the base; enrichment adds the keys below but the upstream shape
    is partially out of our control."""

    schema_version: str
    contract_kind: str
    deterministic: bool
    tree_id: str
    tree_label: str
    root_node_id: Any
    current_window: Window
    comparison_window: Window
    current_value: Any
    comparison_value: Any
    delta_value: Any
    delta_ratio: Any
    unit: str
    grain: str
    window_metadata: WindowMetadata
    normalized_delta_value: float
    normalized_delta_ratio: float | None
    provenance: Provenance
    findings: list[dict[str, Any]]
    time_slices: list[dict[str, Any]]
    mix_shift: dict[str, Any]
    conclusion: dict[str, Any]
    dimensions_considered: list[str]
    time_slice_grain: str
    warnings: list[Any]


class _MaterialityContext(TypedDict):
    tree_id: str
    root_delta: Any
    unit: str
    grain: str
    current_days: int | None
    comparison_days: int | None
    windows_differ: bool


def enrich_rca_output(data: dict[str, Any], config: QluentConfig) -> RCAOutput:
    """Add agent-ready materiality, normalization, and provenance metadata."""
    enriched: RCAOutput = deepcopy(data)  # type: ignore[assignment]
    tree_id = str(enriched.get("tree_id") or "")
    current_window = enriched.get("current_window")
    comparison_window = enriched.get("comparison_window")
    current_days = inclusive_day_count(current_window)
    comparison_days = inclusive_day_count(comparison_window)
    windows_differ = bool(current_days and comparison_days and current_days != comparison_days)
    root_delta = enriched.get("delta_value")
    unit = enriched.get("unit") or "unknown"
    grain = enriched.get("grain") or enriched.get("time_slice_grain") or "unknown"

    enriched.update(
        {
            "schema_version": RCA_SCHEMA_VERSION,
            "contract_kind": "deterministic_rca",
            "deterministic": True,
            "unit": unit,
            "grain": grain,
            "window_metadata": _window_metadata(
                enriched,
                current_days,
                comparison_days,
                windows_differ,
            ),
            "provenance": provenance(
                source="metric_tree_root_cause",
                project_uuid=config.project_uuid,
                tree_id=tree_id,
                node_id=str(enriched.get("root_node_id") or tree_id),
            ),
        }
    )
    _add_normalized_delta(enriched, current_days, comparison_days, windows_differ)

    materiality_context: _MaterialityContext = {
        "tree_id": tree_id,
        "root_delta": root_delta,
        "unit": unit,
        "grain": grain,
        "current_days": current_days,
        "comparison_days": comparison_days,
        "windows_differ": windows_differ,
    }
    _enrich_findings(enriched, config, materiality_context)
    _enrich_time_slices(enriched, config, materiality_context)
    _enrich_mix_shift(enriched, config, materiality_context)
    _enrich_takeaways(enriched, config, tree_id)

    return enriched


def _window_metadata(
    data: dict[str, Any],
    current_days: int | None,
    comparison_days: int | None,
    windows_differ: bool,
) -> WindowMetadata:
    current_window = data.get("current_window") or {}
    comparison_window = data.get("comparison_window") or {}
    return {
        "current_day_count": current_days,
        "comparison_day_count": comparison_days,
        "normalized_delta_included": windows_differ,
        "current_partial_period": bool(
            data.get("current_partial_period")
            or current_window.get("partial_period")
            or current_window.get("is_partial")
        ),
        "comparison_partial_period": bool(
            data.get("comparison_partial_period")
            or comparison_window.get("partial_period")
            or comparison_window.get("is_partial")
        ),
        "current_window_zero_or_null": data.get("current_value") in (None, 0),
        "comparison_window_zero_or_null": data.get("comparison_value") in (None, 0),
    }


def _add_normalized_delta(
    item: dict[str, Any],
    current_days: int | None,
    comparison_days: int | None,
    windows_differ: bool,
) -> None:
    if not windows_differ or not current_days or not comparison_days:
        return
    if not isinstance(item.get("current_value"), (int, float)) or not isinstance(
        item.get("comparison_value"), (int, float)
    ):
        return
    current_per_day = item["current_value"] / current_days
    comparison_per_day = item["comparison_value"] / comparison_days
    item["normalized_delta_value"] = current_per_day - comparison_per_day
    item["normalized_delta_ratio"] = (
        None if comparison_per_day == 0 else (current_per_day - comparison_per_day) / comparison_per_day
    )


def _add_materiality(
    item: dict[str, Any],
    config: QluentConfig,
    context: _MaterialityContext,
    *,
    node_id: str | None = None,
) -> None:
    delta = item.get("delta_value")
    contribution = item.get("contribution_value", delta)
    root_delta = context["root_delta"]
    if item.get("share_of_parent_delta") is None:
        item["share_of_parent_delta"] = item.get("contribution_share")
    if item.get("share_of_root_delta") is None:
        item["share_of_root_delta"] = item.get("share_of_change")
        if (
            item["share_of_root_delta"] is None
            and isinstance(contribution, (int, float))
            and isinstance(root_delta, (int, float))
            and root_delta != 0
        ):
            item["share_of_root_delta"] = contribution / root_delta
    _add_normalized_delta(
        item,
        context["current_days"],
        context["comparison_days"],
        context["windows_differ"],
    )
    item["unit"] = item.get("unit") or context["unit"]
    item["grain"] = item.get("grain") or context["grain"]
    item["provenance"] = item.get("provenance") or provenance(
        source="metric_tree_root_cause",
        project_uuid=config.project_uuid,
        tree_id=context["tree_id"],
        node_id=node_id or item.get("node_id"),
    )


def _enrich_findings(
    data: dict[str, Any],
    config: QluentConfig,
    context: _MaterialityContext,
) -> None:
    for finding in data.get("findings") or []:
        _add_materiality(finding, config, context, node_id=finding.get("node_id"))
        for segment in finding.get("segment_findings") or []:
            _add_materiality(segment, config, context, node_id=finding.get("node_id"))
        for contributor in finding.get("direct_contributors") or []:
            _add_materiality(
                contributor,
                config,
                context,
                node_id=contributor.get("node_id"),
            )


def _enrich_time_slices(
    data: dict[str, Any],
    config: QluentConfig,
    context: _MaterialityContext,
) -> None:
    for slice_result in data.get("time_slices") or []:
        _add_materiality(slice_result, config, context)
        for contributor in slice_result.get("top_contributors") or []:
            _add_materiality(contributor, config, context, node_id=contributor.get("node_id"))


def _enrich_mix_shift(
    data: dict[str, Any],
    config: QluentConfig,
    context: _MaterialityContext,
) -> None:
    mix_shift = data.get("mix_shift") or {}
    for segment in mix_shift.get("segments") or []:
        _add_materiality(segment, config, context)


def _enrich_takeaways(data: dict[str, Any], config: QluentConfig, tree_id: str) -> None:
    conclusion = data.get("conclusion") or {}
    for takeaway in conclusion.get("takeaways") or []:
        takeaway["provenance"] = takeaway.get("provenance") or provenance(
            source="metric_tree_root_cause",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=takeaway.get("node_id"),
        )
