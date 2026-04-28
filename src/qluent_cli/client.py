"""HTTP client for the Qluent metric tree API."""

from __future__ import annotations

import os
import random
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from qluent_cli.config import QluentConfig
from qluent_cli.output import echo_status


_INVESTIGATE_TIMEOUT = 300.0
_PROGRESS_INTERVAL_SECONDS = 30.0
ProgressCallback = Callable[[str, float], None]

_RETRYABLE_STATUS = frozenset({408, 429, 502, 503, 504})
_CONNECTION_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
)
_RESPONSE_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
_RETRYABLE_EXCEPTIONS = _CONNECTION_RETRYABLE_EXCEPTIONS + _RESPONSE_RETRYABLE_EXCEPTIONS
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DEFAULT_BACKOFF: tuple[float, ...] = (0.5, 1.5, 4.0)


def _parse_retry_after(value: str) -> float | None:
    """Parse an HTTP Retry-After header value (delta-seconds or HTTP-date)."""
    value = value.strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())


def _default_log(attempt: int, retries: int, reason: str, delay: float) -> None:
    if os.environ.get("QLUENT_QUIET"):
        return
    echo_status(f"[qluent] retry {attempt}/{retries} after {reason} in {delay:.1f}s")


class _RetryTransport(httpx.BaseTransport):
    """Wraps an httpx transport with retries for transient failures.

    Connection errors are retried on all methods because no bytes were sent.
    Read/protocol errors and retryable status codes are only retried on
    idempotent methods, so a side-effecting POST is never replayed after it
    may have reached the server. Honors Retry-After on 429/503.
    """

    def __init__(
        self,
        wrapped: httpx.BaseTransport,
        *,
        backoff: tuple[float, ...] = _DEFAULT_BACKOFF,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[int, int, str, float], None] = _default_log,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._backoff = backoff
        self._sleep = sleep
        self._log = log
        self._jitter = jitter if jitter is not None else _default_jitter

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        retries = len(self._backoff)
        is_idempotent = request.method.upper() in _IDEMPOTENT_METHODS

        for attempt in range(retries + 1):
            try:
                response = self._wrapped.handle_request(request)
            except _RETRYABLE_EXCEPTIONS as exc:
                if (
                    not is_idempotent
                    and not isinstance(exc, _CONNECTION_RETRYABLE_EXCEPTIONS)
                ):
                    raise
                if attempt >= retries:
                    raise
                delay = self._jitter(self._backoff[attempt])
                self._log(attempt + 1, retries, type(exc).__name__, delay)
                self._sleep(delay)
                continue

            if response.status_code not in _RETRYABLE_STATUS:
                return response
            if not is_idempotent:
                return response
            if attempt >= retries:
                return response

            retry_after = response.headers.get("Retry-After")
            base = _parse_retry_after(retry_after) if retry_after else None
            if base is None:
                delay = self._jitter(self._backoff[attempt])
            else:
                delay = base
            self._log(attempt + 1, retries, str(response.status_code), delay)
            response.close()
            self._sleep(delay)

        return response  # pragma: no cover

    def close(self) -> None:
        self._wrapped.close()


def _default_jitter(base: float) -> float:
    return base * random.uniform(0.7, 1.3)


def _build_transport() -> httpx.BaseTransport:
    return _RetryTransport(httpx.HTTPTransport())


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
            transport=_build_transport(),
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
        metric: str | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
    ) -> dict[str, Any]:
        body = self._window_body(current_from, current_to, comparison_from, comparison_to)
        body.update({
            "segment_by": segment_by or [],
            "filters": filters or {},
            "metric": metric,
            "max_depth": max_depth,
            "max_branching": max_branching,
            "max_segments": max_segments,
            "min_contribution_share": min_contribution_share,
        })
        if metric is None:
            body.pop("metric")
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

    def investigate_tree(
        self,
        tree_id: str,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
        *,
        trend_periods: int = 4,
        trend_grain: str = "week",
        trend_as_of: str | None = None,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        metric: str | None = None,
        compare_trees: list[str] | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run a full server-side investigation bundle."""
        body = self._rca_body(
            current_from, current_to, comparison_from, comparison_to,
            segment_by=segment_by, filters=filters, metric=metric,
            max_depth=max_depth, max_branching=max_branching,
            max_segments=max_segments, min_contribution_share=min_contribution_share,
        )
        body.update({
            "trend_periods": trend_periods,
            "trend_grain": trend_grain,
            "trend_as_of": trend_as_of,
            "compare_trees": compare_trees or [],
        })
        resp = self._post_with_progress(
            f"{self._base}/metric-trees/{tree_id}/investigate/",
            json=body,
            timeout=_INVESTIGATE_TIMEOUT,
            progress_callback=progress_callback,
        )
        resp.raise_for_status()
        return resp.json()

    def _post_with_progress(
        self,
        url: str,
        *,
        json: dict[str, Any],
        timeout: float,
        progress_callback: ProgressCallback | None,
    ) -> httpx.Response:
        if progress_callback is None:
            return self._client.post(url, json=json, timeout=timeout)

        started = time.monotonic()
        done = threading.Event()

        def tick() -> None:
            while not done.wait(_PROGRESS_INTERVAL_SECONDS):
                progress_callback("awaiting_api", time.monotonic() - started)

        thread = threading.Thread(target=tick, daemon=True)
        thread.start()
        try:
            return self._client.post(url, json=json, timeout=timeout)
        finally:
            done.set()

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
        metric: str | None = None,
        max_depth: int = 3,
        max_branching: int = 2,
        max_segments: int = 5,
        min_contribution_share: float = 0.1,
    ) -> dict[str, Any]:
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/root-cause/",
            json=self._rca_body(
                current_from, current_to, comparison_from, comparison_to,
                segment_by=segment_by, filters=filters, metric=metric,
                max_depth=max_depth, max_branching=max_branching,
                max_segments=max_segments, min_contribution_share=min_contribution_share,
            ),
        )
        resp.raise_for_status()
        return resp.json()

    def elasticity_tree(
        self,
        tree_id: str,
        current_from: str,
        current_to: str,
        comparison_from: str,
        comparison_to: str,
        *,
        outcome: str,
        lever: str,
        dimension: str | None = None,
        filters: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        body = self._window_body(current_from, current_to, comparison_from, comparison_to)
        body.update({
            "outcome": outcome,
            "lever": lever,
            "dimension": dimension,
            "filters": filters or {},
        })
        if dimension is None:
            body.pop("dimension")
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/elasticity/",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()
