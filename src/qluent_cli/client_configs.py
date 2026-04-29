"""Domain-shaped configs for client requests.

The client used to take long kwargs lists and defaults lived in three
places (Click options, MCP schemas, client method signatures).  These
dataclasses make the defaults canonical and the call sites legible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RcaParams:
    """Parameters shared by `root_cause_tree` and `investigate_tree`."""

    metric: str | None = None
    segment_by: tuple[str, ...] = ()
    filters: dict[str, list[str]] = field(default_factory=dict)
    max_depth: int = 3
    max_branching: int = 2
    max_segments: int = 5
    min_contribution_share: float = 0.1


@dataclass(frozen=True)
class InvestigationParams:
    """Investigation-specific options layered on top of RCA params.

    Investigation = RCA + multi-period trend + cross-tree comparison.
    """

    metric: str | None = None
    segment_by: tuple[str, ...] = ()
    filters: dict[str, list[str]] = field(default_factory=dict)
    max_depth: int = 3
    max_branching: int = 2
    max_segments: int = 5
    min_contribution_share: float = 0.1
    trend_periods: int = 4
    trend_grain: str = "week"
    trend_as_of: str | None = None
    compare_trees: tuple[str, ...] = ()

    def as_rca(self) -> RcaParams:
        return RcaParams(
            metric=self.metric,
            segment_by=self.segment_by,
            filters=self.filters,
            max_depth=self.max_depth,
            max_branching=self.max_branching,
            max_segments=self.max_segments,
            min_contribution_share=self.min_contribution_share,
        )


@dataclass(frozen=True)
class ElasticityParams:
    """Parameters for the elasticity endpoint."""

    outcome: str
    lever: str
    dimension: str | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)


def rca_params_to_kwargs(params: RcaParams) -> dict[str, Any]:
    """Adapt an `RcaParams` into the kwargs the wire-level helpers accept."""
    return {
        "metric": params.metric,
        "segment_by": list(params.segment_by),
        "filters": dict(params.filters),
        "max_depth": params.max_depth,
        "max_branching": params.max_branching,
        "max_segments": params.max_segments,
        "min_contribution_share": params.min_contribution_share,
    }
