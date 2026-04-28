"""Stable JSON contract for deterministic metric tree queries."""

from __future__ import annotations

from typing import Any, TypedDict

from qluent_cli.config import QluentConfig
from qluent_cli.contract_helpers import (
    ProjectContext,
    Provenance,
    Window,
    inclusive_day_count,
    provenance,
)


TREE_QUERY_SCHEMA_VERSION = "qluent.tree_query.v1"


class MetricValue(TypedDict):
    value: Any
    unit: str
    grain: str
    window: Window | None
    provenance: Provenance


class MetricDelta(TypedDict):
    value: Any
    ratio: Any
    unit: str
    grain: str
    current_window: Window | None
    comparison_window: Window | None
    provenance: Provenance


class NodeMetricValue(TypedDict, total=False):
    node_id: str
    label: str
    kind: str | None
    current: MetricValue
    comparison: MetricValue
    delta: MetricDelta


class RootMetric(TypedDict):
    id: str
    label: str
    unit: str


class TreeRef(TypedDict):
    id: str
    label: str
    root_node_id: Any


class TreeWindows(TypedDict):
    current: Window | None
    comparison: Window | None
    current_day_count: int | None
    comparison_day_count: int | None


class TreeQueryContract(TypedDict):
    schema_version: str
    contract_kind: str
    deterministic: bool
    agent_interpretation: Any
    project_context: ProjectContext
    tree: TreeRef
    root_metric: RootMetric
    grain: str
    dimensions: list[Any]
    filters: dict[str, Any]
    windows: TreeWindows
    metric_values: list[NodeMetricValue]
    child_decomposition: list[Any]
    dimension_breakdowns: list[Any]
    warnings: list[Any]
    provenance: Provenance


def _metric_value(
    *,
    value: Any,
    unit: str | None,
    grain: str | None,
    window: Window | None,
    value_provenance: Provenance,
) -> MetricValue:
    return {
        "value": value,
        "unit": unit or "unknown",
        "grain": grain or "unknown",
        "window": window,
        "provenance": value_provenance,
    }


def build_tree_query_contract(
    evaluation: dict[str, Any],
    config: QluentConfig,
    *,
    filters: dict[str, list[str]] | None = None,
) -> TreeQueryContract:
    """Convert a tree evaluation response into the deterministic query contract."""
    tree_id = str(evaluation.get("tree_id") or "")
    root_node_id = evaluation.get("root_node_id")
    grain = evaluation.get("grain") or evaluation.get("time_grain")
    unit = evaluation.get("unit")
    current_window = evaluation.get("current_window")
    comparison_window = evaluation.get("comparison_window")

    nodes = evaluation.get("nodes") or []
    root_node = next((node for node in nodes if node.get("id") == root_node_id), None)
    root_metric: RootMetric = {
        "id": root_node_id or tree_id,
        "label": evaluation.get("tree_label") or (root_node or {}).get("label") or tree_id,
        "unit": (root_node or {}).get("unit") or unit or "unknown",
    }

    metric_values = _build_node_metric_values(
        nodes,
        config=config,
        tree_id=tree_id,
        unit=unit,
        grain=grain,
        current_window=current_window,
        comparison_window=comparison_window,
    )
    if not metric_values:
        metric_values = [
            _build_root_metric_value(
                evaluation,
                config=config,
                tree_id=tree_id,
                root_metric=root_metric,
                unit=unit,
                grain=grain,
                current_window=current_window,
                comparison_window=comparison_window,
            )
        ]

    project_context: ProjectContext = {
        "project_uuid": config.project_uuid,
        "user_email": config.user_email,
        "api_url": config.api_url,
        "client_safe": config.client_safe,
    }

    return {
        "schema_version": TREE_QUERY_SCHEMA_VERSION,
        "contract_kind": "deterministic_tree_query",
        "deterministic": True,
        "agent_interpretation": None,
        "project_context": project_context,
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
            "current_day_count": inclusive_day_count(current_window),
            "comparison_day_count": inclusive_day_count(comparison_window),
        },
        "metric_values": metric_values,
        "child_decomposition": evaluation.get("top_contributors") or [],
        "dimension_breakdowns": evaluation.get("dimension_breakdowns") or evaluation.get("segments") or [],
        "warnings": evaluation.get("warnings") or [],
        "provenance": provenance(
            source="metric_tree_evaluate",
            project_uuid=config.project_uuid,
            tree_id=tree_id,
            node_id=str(root_metric["id"]),
        ),
    }


def _build_node_metric_values(
    nodes: list[dict[str, Any]],
    *,
    config: QluentConfig,
    tree_id: str,
    unit: str | None,
    grain: str | None,
    current_window: Window | None,
    comparison_window: Window | None,
) -> list[NodeMetricValue]:
    metric_values: list[NodeMetricValue] = []
    for node in nodes:
        node_id = str(node.get("id") or node.get("node_id") or "")
        node_unit = node.get("unit") or unit
        node_grain = node.get("grain") or grain
        node_provenance = provenance(
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
                    value_provenance=node_provenance,
                ),
                "comparison": _metric_value(
                    value=node.get("comparison_value"),
                    unit=node_unit,
                    grain=node_grain,
                    window=comparison_window,
                    value_provenance=node_provenance,
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
    return metric_values


def _build_root_metric_value(
    evaluation: dict[str, Any],
    *,
    config: QluentConfig,
    tree_id: str,
    root_metric: RootMetric,
    unit: str | None,
    grain: str | None,
    current_window: Window | None,
    comparison_window: Window | None,
) -> NodeMetricValue:
    root_provenance = provenance(
        source="metric_tree_evaluate",
        project_uuid=config.project_uuid,
        tree_id=tree_id,
        node_id=str(root_metric["id"]),
    )
    return {
        "node_id": root_metric["id"],
        "label": root_metric["label"],
        "kind": "root",
        "current": _metric_value(
            value=evaluation.get("current_value"),
            unit=unit,
            grain=grain,
            window=current_window,
            value_provenance=root_provenance,
        ),
        "comparison": _metric_value(
            value=evaluation.get("comparison_value"),
            unit=unit,
            grain=grain,
            window=comparison_window,
            value_provenance=root_provenance,
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
