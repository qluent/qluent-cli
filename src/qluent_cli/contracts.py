"""Stable JSON contracts for agent-facing metric tree outputs."""

from __future__ import annotations

from copy import deepcopy
from datetime import date as dt_date
from typing import Any

from qluent_cli.config import QluentConfig


TREE_QUERY_SCHEMA_VERSION = "qluent.tree_query.v1"
RCA_SCHEMA_VERSION = "qluent.rca.v1"


def _inclusive_day_count(window: dict[str, Any] | None) -> int | None:
    if not window:
        return None
    try:
        start = dt_date.fromisoformat(str(window["date_from"]))
        end = dt_date.fromisoformat(str(window["date_to"]))
    except (KeyError, ValueError, TypeError):
        return None
    return (end - start).days + 1


def _provenance(
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


def _metric_value(
    *,
    value: Any,
    unit: str | None,
    grain: str | None,
    window: dict[str, Any] | None,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit or "unknown",
        "grain": grain or "unknown",
        "window": window,
        "provenance": provenance,
    }


def build_tree_query_contract(
    evaluation: dict[str, Any],
    config: QluentConfig,
    *,
    filters: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Convert a tree evaluation response into the deterministic query contract."""
    tree_id = str(evaluation.get("tree_id") or "")
    root_node_id = evaluation.get("root_node_id")
    grain = evaluation.get("grain") or evaluation.get("time_grain")
    unit = evaluation.get("unit")
    current_window = evaluation.get("current_window")
    comparison_window = evaluation.get("comparison_window")

    nodes = evaluation.get("nodes") or []
    root_node = next((node for node in nodes if node.get("id") == root_node_id), None)
    root_metric = {
        "id": root_node_id or tree_id,
        "label": evaluation.get("tree_label") or (root_node or {}).get("label") or tree_id,
        "unit": (root_node or {}).get("unit") or unit or "unknown",
    }

    metric_values: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or node.get("node_id") or "")
        node_unit = node.get("unit") or unit
        node_grain = node.get("grain") or grain
        node_provenance = _provenance(
            source="metric_tree_evaluate",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=node_id,
            metric_id=node.get("metric_id"),
        )
        metric_values.append(
            {
                "node_id": node_id,
                "label": node.get("label") or node_id,
                "kind": node.get("kind"),
                "current": _metric_value(
                    value=node.get("current_value"),
                    unit=node_unit,
                    grain=node_grain,
                    window=current_window,
                    provenance=node_provenance,
                ),
                "comparison": _metric_value(
                    value=node.get("comparison_value"),
                    unit=node_unit,
                    grain=node_grain,
                    window=comparison_window,
                    provenance=node_provenance,
                ),
                "delta": {
                    "value": node.get("delta_value"),
                    "ratio": node.get("delta_ratio"),
                    "unit": node_unit or "unknown",
                    "grain": node_grain or "unknown",
                    "current_window": current_window,
                    "comparison_window": comparison_window,
                    "provenance": node_provenance,
                },
            }
        )

    if not metric_values:
        root_provenance = _provenance(
            source="metric_tree_evaluate",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=str(root_metric["id"]),
        )
        metric_values.append(
            {
                "node_id": root_metric["id"],
                "label": root_metric["label"],
                "kind": "root",
                "current": _metric_value(
                    value=evaluation.get("current_value"),
                    unit=unit,
                    grain=grain,
                    window=current_window,
                    provenance=root_provenance,
                ),
                "comparison": _metric_value(
                    value=evaluation.get("comparison_value"),
                    unit=unit,
                    grain=grain,
                    window=comparison_window,
                    provenance=root_provenance,
                ),
                "delta": {
                    "value": evaluation.get("delta_value"),
                    "ratio": evaluation.get("delta_ratio"),
                    "unit": unit or "unknown",
                    "grain": grain or "unknown",
                    "current_window": current_window,
                    "comparison_window": comparison_window,
                    "provenance": root_provenance,
                },
            }
        )

    return {
        "schema_version": TREE_QUERY_SCHEMA_VERSION,
        "contract_kind": "deterministic_tree_query",
        "deterministic": True,
        "agent_interpretation": None,
        "project_context": {
            "project_uuid": config.project_uuid,
            "user_email": config.user_email,
            "api_url": config.api_url,
            "client_safe": config.client_safe,
        },
        "tree": {
            "id": tree_id,
            "label": evaluation.get("tree_label") or tree_id,
            "root_node_id": root_node_id,
        },
        "root_metric": root_metric,
        "grain": grain or "unknown",
        "dimensions": evaluation.get("dimensions") or evaluation.get("dimensions_considered") or [],
        "filters": filters or evaluation.get("filters") or {},
        "windows": {
            "current": current_window,
            "comparison": comparison_window,
            "current_day_count": _inclusive_day_count(current_window),
            "comparison_day_count": _inclusive_day_count(comparison_window),
        },
        "metric_values": metric_values,
        "child_decomposition": evaluation.get("top_contributors") or [],
        "dimension_breakdowns": evaluation.get("dimension_breakdowns") or evaluation.get("segments") or [],
        "warnings": evaluation.get("warnings") or [],
        "provenance": _provenance(
            source="metric_tree_evaluate",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=str(root_metric["id"]),
        ),
    }


def enrich_rca_output(data: dict[str, Any], config: QluentConfig) -> dict[str, Any]:
    """Add agent-ready materiality, normalization, and provenance metadata."""
    enriched = deepcopy(data)
    tree_id = str(enriched.get("tree_id") or "")
    current_window = enriched.get("current_window")
    comparison_window = enriched.get("comparison_window")
    current_days = _inclusive_day_count(current_window)
    comparison_days = _inclusive_day_count(comparison_window)
    windows_differ = bool(current_days and comparison_days and current_days != comparison_days)
    root_delta = enriched.get("delta_value")
    unit = enriched.get("unit") or "unknown"
    grain = enriched.get("grain") or enriched.get("time_slice_grain") or "unknown"

    enriched["schema_version"] = RCA_SCHEMA_VERSION
    enriched["contract_kind"] = "deterministic_rca"
    enriched["deterministic"] = True
    enriched["unit"] = unit
    enriched["grain"] = grain
    enriched["window_metadata"] = {
        "current_day_count": current_days,
        "comparison_day_count": comparison_days,
        "normalized_delta_included": windows_differ,
        "current_partial_period": bool(
            enriched.get("current_partial_period")
            or (current_window or {}).get("partial_period")
            or (current_window or {}).get("is_partial")
        ),
        "comparison_partial_period": bool(
            enriched.get("comparison_partial_period")
            or (comparison_window or {}).get("partial_period")
            or (comparison_window or {}).get("is_partial")
        ),
        "current_window_zero_or_null": enriched.get("current_value") in (None, 0),
        "comparison_window_zero_or_null": enriched.get("comparison_value") in (None, 0),
    }
    enriched["provenance"] = _provenance(
        source="metric_tree_root_cause",
        project_uuid=config.project_uuid,
        tree_id=tree_id,
        node_id=str(enriched.get("root_node_id") or tree_id),
    )

    if windows_differ and isinstance(enriched.get("current_value"), (int, float)) and isinstance(enriched.get("comparison_value"), (int, float)):
        current_per_day = enriched["current_value"] / current_days
        comparison_per_day = enriched["comparison_value"] / comparison_days
        enriched["normalized_delta_value"] = current_per_day - comparison_per_day
        enriched["normalized_delta_ratio"] = (
            None if comparison_per_day == 0 else (current_per_day - comparison_per_day) / comparison_per_day
        )

    def add_materiality(item: dict[str, Any], *, node_id: str | None = None) -> None:
        delta = item.get("delta_value")
        contribution = item.get("contribution_value", delta)
        if item.get("share_of_parent_delta") is None:
            item["share_of_parent_delta"] = item.get("contribution_share")
        if item.get("share_of_root_delta") is None:
            item["share_of_root_delta"] = item.get("share_of_change")
            if item["share_of_root_delta"] is None and isinstance(contribution, (int, float)) and isinstance(root_delta, (int, float)) and root_delta != 0:
                item["share_of_root_delta"] = contribution / root_delta
        if windows_differ and isinstance(item.get("current_value"), (int, float)) and isinstance(item.get("comparison_value"), (int, float)):
            item_current = item["current_value"] / current_days
            item_comparison = item["comparison_value"] / comparison_days
            item["normalized_delta_value"] = item_current - item_comparison
            item["normalized_delta_ratio"] = None if item_comparison == 0 else (item_current - item_comparison) / item_comparison
        item["unit"] = item.get("unit") or unit
        item["grain"] = item.get("grain") or grain
        item["provenance"] = item.get("provenance") or _provenance(
            source="metric_tree_root_cause",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=node_id or item.get("node_id"),
        )

    for finding in enriched.get("findings") or []:
        add_materiality(finding, node_id=finding.get("node_id"))
        for segment in finding.get("segment_findings") or []:
            add_materiality(segment, node_id=finding.get("node_id"))
        for contributor in finding.get("direct_contributors") or []:
            add_materiality(contributor, node_id=contributor.get("node_id"))

    for slice_result in enriched.get("time_slices") or []:
        add_materiality(slice_result)
        for contributor in slice_result.get("top_contributors") or []:
            add_materiality(contributor, node_id=contributor.get("node_id"))

    mix_shift = enriched.get("mix_shift") or {}
    for segment in mix_shift.get("segments") or []:
        add_materiality(segment)

    conclusion = enriched.get("conclusion") or {}
    for takeaway in conclusion.get("takeaways") or []:
        takeaway["provenance"] = takeaway.get("provenance") or _provenance(
            source="metric_tree_root_cause",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=takeaway.get("node_id"),
        )

    return enriched
