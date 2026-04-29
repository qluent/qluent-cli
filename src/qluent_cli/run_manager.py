"""RunManager — owns the investigation lifecycle.

Today the investigate flow is split:

    trees.py:investigate
        -> builds RunReporter
        -> calls run_investigation (sanitize)
        -> calls _persist_run_safely
        -> calls _emit_investigation

    mcp_server.py:_investigate
        -> calls run_investigation (sanitize)

Both adapters re-implement the same dance.  The deepening: a `RunManager`
that owns reporter + persistence + sanitization as one unit.  Adapters say
"investigate this tree under these constraints" and get back a finished,
persisted result.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from qluent_cli import sessions
from qluent_cli.client import QluentClient
from qluent_cli.client_configs import InvestigationParams
from qluent_cli.config import QluentConfig
from qluent_cli.dates import DateWindows
from qluent_cli.runs import (
    RunReporter,
    collect_tree_metadata,
    sanitize_recommended_next_steps,
)


@dataclass
class RunResult:
    """The finished result of an investigation."""

    bundle: dict[str, Any]
    run_id: str | None
    from_cache: bool = False


class RunManager:
    """Encapsulates the investigation lifecycle for one or many trees."""

    INVESTIGATE_COMMAND = sessions.INVESTIGATE_COMMAND

    def __init__(
        self,
        client: QluentClient,
        config: QluentConfig,
        *,
        persist: bool = True,
    ) -> None:
        self._client = client
        self._config = config
        self._persist = persist

    def investigate(
        self,
        tree_id: str,
        *,
        windows: DateWindows,
        params: InvestigationParams,
        reporter: RunReporter | None = None,
        original_args: dict[str, Any] | None = None,
    ) -> RunResult:
        """Run a single tree investigation: client call -> sanitize -> persist."""
        c_from, c_to, p_from, p_to = windows.iso_tuple()
        trees_data = self._client.list_trees()
        if reporter is not None:
            reporter.progress("awaiting_api")

        bundle = self._client.investigate_tree(
            tree_id,
            windows=windows,
            params=params,
            progress_callback=(
                (lambda stage, elapsed: reporter.progress(stage, elapsed=elapsed))
                if reporter is not None
                else None
            ),
        )
        if reporter is not None:
            reporter.progress("formatting")

        available_tree_ids, metrics_by_tree = collect_tree_metadata(trees_data)
        sanitize_recommended_next_steps(
            bundle,
            available_tree_ids=available_tree_ids,
            metrics_by_tree=metrics_by_tree,
        )

        record = self._maybe_persist(
            tree_id=tree_id,
            c_from=c_from,
            c_to=c_to,
            p_from=p_from,
            p_to=p_to,
            params=params,
            bundle=bundle,
            original_args=original_args or {},
        )
        return RunResult(
            bundle=bundle,
            run_id=record.run_id if record else sessions.generate_run_id(),
            from_cache=False,
        )

    def _maybe_persist(
        self,
        *,
        tree_id: str,
        c_from: str,
        c_to: str,
        p_from: str,
        p_to: str,
        params: InvestigationParams,
        bundle: dict[str, Any],
        original_args: dict[str, Any],
    ):
        if not self._persist:
            return None
        try:
            return sessions.record_run(
                command=self.INVESTIGATE_COMMAND,
                tree_id=tree_id,
                period_start=c_from,
                period_end=c_to,
                comparison_start=p_from,
                comparison_end=p_to,
                profile=f"{self._config.user_email}@{self._config.api_url}",
                client_safe=self._config.client_safe,
                args={
                    "trend_periods": params.trend_periods,
                    "trend_grain": params.trend_grain,
                    "trend_as_of": params.trend_as_of,
                    "segment_by": list(params.segment_by),
                    "filters": dict(params.filters),
                    "compare_trees": list(params.compare_trees),
                    "max_depth": params.max_depth,
                    "max_branches": params.max_branching,
                    "max_segments": params.max_segments,
                    "min_contribution_share": params.min_contribution_share,
                    **original_args,
                },
                payload=bundle,
            )
        except Exception as exc:
            print(f"Warning: failed to persist run: {exc}", file=sys.stderr)
            return None
