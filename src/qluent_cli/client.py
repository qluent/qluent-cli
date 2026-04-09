"""HTTP client for the Qluent metric tree API."""

from __future__ import annotations

from typing import Any

import httpx

from qluent_cli.config import QluentConfig


_INVESTIGATE_TIMEOUT = 300.0


class QluentClient:
    """Thin wrapper around the Qluent external API."""

    def __init__(self, config: QluentConfig) -> None:
        self._config = config
        self._base = f"{config.api_url}/api/v1/project/{config.project_uuid}"
        headers: dict[str, str] = {}
        if config.api_key:
            headers["X-API-Key"] = config.api_key
        if config.client_safe:
            headers["X-Qluent-Client-Safe"] = "true"
        self._client = httpx.Client(
            headers=headers,
            timeout=120.0,
        )

    def _window_body(
        self,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
    ) -> dict[str, Any]:
        return {
            "user_email": self._config.user_email,
            "current_window": {"date_from": current_from, "date_to": current_to},
            "comparison_window": {"date_from": comparison_from, "date_to": comparison_to},
        }

    def _rca_body(
        self,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
        *,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
    ) -> dict[str, Any]:
        body = self._window_body(current_from, current_to, comparison_from, comparison_to)
        body.update({
            "segment_by": segment_by or [],
            "filters": filters or {},
            "max_depth": max_depth,
            "max_branching": max_branching,
            "max_segments": max_segments,
            "min_contribution_share": min_contribution_share,
        })
        return body

    def list_trees(self) -> dict[str, Any]:
        resp = self._client.get(
            f"{self._base}/metric-trees/",
            params={"user_email": self._config.user_email},
        )
        resp.raise_for_status()
        return resp.json()

    def get_tree(self, tree_id: str) -> dict[str, Any]:
        resp = self._client.get(
            f"{self._base}/metric-trees/{tree_id}/",
            params={"user_email": self._config.user_email},
        )
        resp.raise_for_status()
        return resp.json()

    def validate_tree(self, tree_id: str) -> dict[str, Any]:
        resp = self._client.get(
            f"{self._base}/metric-trees/{tree_id}/validate/",
            params={"user_email": self._config.user_email},
        )
        resp.raise_for_status()
        return resp.json()

    def evaluate_tree(
        self,
        tree_id: str,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/evaluate/",
            json=self._window_body(current_from, current_to, comparison_from, comparison_to),
        )
        resp.raise_for_status()
        return resp.json()

    def match_tree(self, question: str) -> dict[str, Any]:
        """Match a natural-language question to the best metric tree (server-side)."""
        resp = self._client.post(
            f"{self._base}/metric-trees/match/",
            json={
                "user_email": self._config.user_email,
                "question": question,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def investigate_tree(
        self,
        tree_id: str,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
        *,
        question: str | None = None,
        trend_periods: int = 4,
        trend_grain: str = "week",
        trend_as_of: str | None = None,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        compare_trees: list[str] | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
    ) -> dict[str, Any]:
        """Run a full server-side investigation bundle."""
        body = self._rca_body(
            current_from, current_to, comparison_from, comparison_to,
            segment_by=segment_by, filters=filters,
            max_depth=max_depth, max_branching=max_branching,
            max_segments=max_segments, min_contribution_share=min_contribution_share,
        )
        body.update({
            "question": question,
            "trend_periods": trend_periods,
            "trend_grain": trend_grain,
            "trend_as_of": trend_as_of,
            "compare_trees": compare_trees or [],
        })
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/investigate/",
            json=body,
            timeout=_INVESTIGATE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def root_cause_tree(
        self,
        tree_id: str,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
        *,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/root-cause/",
            json=self._rca_body(
                current_from, current_to, comparison_from, comparison_to,
                segment_by=segment_by, filters=filters,
                max_depth=max_depth, max_branching=max_branching,
                max_segments=max_segments, min_contribution_share=min_contribution_share,
            ),
        )
        resp.raise_for_status()
        return resp.json()
