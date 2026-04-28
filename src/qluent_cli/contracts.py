"""Compatibility exports for agent-facing output contracts."""

from qluent_cli.contract_helpers import (
    ProjectContext,
    Provenance,
    Window,
    WindowMetadata,
    inclusive_day_count,
    provenance,
)
from qluent_cli.rca_contracts import RCA_SCHEMA_VERSION, RCAOutput, enrich_rca_output
from qluent_cli.tree_contracts import (
    TREE_QUERY_SCHEMA_VERSION,
    MetricDelta,
    MetricValue,
    NodeMetricValue,
    RootMetric,
    TreeQueryContract,
    TreeRef,
    TreeWindows,
    build_tree_query_contract,
)

__all__ = [
    "RCAOutput",
    "RCA_SCHEMA_VERSION",
    "TREE_QUERY_SCHEMA_VERSION",
    "MetricDelta",
    "MetricValue",
    "NodeMetricValue",
    "ProjectContext",
    "Provenance",
    "RootMetric",
    "TreeQueryContract",
    "TreeRef",
    "TreeWindows",
    "Window",
    "WindowMetadata",
    "build_tree_query_contract",
    "enrich_rca_output",
    "inclusive_day_count",
    "provenance",
]
