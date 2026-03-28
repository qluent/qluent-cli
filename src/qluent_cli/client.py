"""HTTP client for the Qluent metric tree API."""

from __future__ import annotations

from typing import Any

import httpx

from qluent_cli.config import QluentConfig


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
            json={
                "user_email": self._config.user_email,
                "current_window": {
                    "date_from": current_from,
                    "date_to": current_to,
                },
                "comparison_window": {
                    "date_from": comparison_from,
                    "date_to": comparison_to,
                },
            },
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
            json={
                "user_email": self._config.user_email,
                "current_window": {
                    "date_from": current_from,
                    "date_to": current_to,
                },
                "comparison_window": {
                    "date_from": comparison_from,
                    "date_to": comparison_to,
                },
                "segment_by": segment_by or [],
                "filters": filters or {},
                "max_depth": max_depth,
                "max_branching": max_branching,
                "max_segments": max_segments,
                "min_contribution_share": min_contribution_share,
            },
        )
        resp.raise_for_status()
        return resp.json()
