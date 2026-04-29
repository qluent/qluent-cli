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

from qluent_cli.client_configs import (
    ElasticityParams,
    InvestigationParams,
    RcaParams,
    rca_params_to_kwargs,
)
from qluent_cli.config import QluentConfig
from qluent_cli.dates import DateWindows
from qluent_cli.output import echo_status
from qluent_cli.rca_contracts import RCAOutput, enrich_rca_output


_INVESTIGATE_TIMEOUT = 300.0
_PROGRESS_INTERVAL_SECONDS = 30.0

# Heartbeat callback used by `investigate_tree` to surface that a long-running
# POST is still in flight. Invoked from a background thread roughly every
# `_PROGRESS_INTERVAL_SECONDS` with `(stage_name, elapsed_seconds)`. Today the
# only emitted stage is "awaiting_api". The callback must be thread-safe and
# non-blocking. Unrelated to retry — retries happen inside the transport and
# are surfaced through `_default_log`, not through this callback.
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


def _windows_to_iso(
    windows: DateWindows | None,
    current_from: str | None,
    current_to: str | None,
    comparison_from: str | None,
    comparison_to: str | None,
) -> tuple[str, str, str, str]:
    """Accept either a `DateWindows` or four positional ISO strings."""
    if windows is not None:
        return windows.iso_tuple()
    if not all([current_from, current_to, comparison_from, comparison_to]):
        raise TypeError(
            "Pass either `windows=DateWindows(...)` or all four of "
            "current_from/current_to/comparison_from/comparison_to."
        )
    return current_from, current_to, comparison_from, comparison_to  # type: ignore[return-value]


def _merge_rca_params(
    params: RcaParams | None,
    *,
    segment_by: list[str] | None,
    filters: dict[str, list[str]] | None,
    metric: str | None,
    max_depth: int | None,
    max_branching: int | None,
    max_segments: int | None,
    min_contribution_share: float | None,
) -> RcaParams:
    """Take an explicit `RcaParams`, falling back to per-kwarg overrides
    when none was provided. Kwargs are kept for adapters that build
    their params iteratively (CLI Click options); the dataclass is the
    canonical shape."""
    if params is None:
        params = RcaParams()
    return RcaParams(
        metric=metric if metric is not None else params.metric,
        segment_by=tuple(segment_by) if segment_by is not None else params.segment_by,
        filters=dict(filters) if filters is not None else params.filters,
        max_depth=max_depth if max_depth is not None else params.max_depth,
        max_branching=max_branching if max_branching is not None else params.max_branching,
        max_segments=max_segments if max_segments is not None else params.max_segments,
        min_contribution_share=(
            min_contribution_share
            if min_contribution_share is not None
            else params.min_contribution_share
        ),
    )


def _merge_investigation_params(
    params: InvestigationParams | None,
    *,
    trend_periods: int | None,
    trend_grain: str | None,
    trend_as_of: str | None,
    segment_by: list[str] | None,
    filters: dict[str, list[str]] | None,
    metric: str | None,
    compare_trees: list[str] | None,
    max_depth: int | None,
    max_branching: int | None,
    max_segments: int | None,
    min_contribution_share: float | None,
) -> InvestigationParams:
    if params is None:
        params = InvestigationParams()
    return InvestigationParams(
        metric=metric if metric is not None else params.metric,
        segment_by=tuple(segment_by) if segment_by is not None else params.segment_by,
        filters=dict(filters) if filters is not None else params.filters,
        max_depth=max_depth if max_depth is not None else params.max_depth,
        max_branching=max_branching if max_branching is not None else params.max_branching,
        max_segments=max_segments if max_segments is not None else params.max_segments,
        min_contribution_share=(
            min_contribution_share
            if min_contribution_share is not None
            else params.min_contribution_share
        ),
        trend_periods=trend_periods if trend_periods is not None else params.trend_periods,
        trend_grain=trend_grain if trend_grain is not None else params.trend_grain,
        trend_as_of=trend_as_of if trend_as_of is not None else params.trend_as_of,
        compare_trees=(
            tuple(compare_trees) if compare_trees is not None else params.compare_trees
        ),
    )


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
        current_from: str | None = None,
        current_to: str | None = None,
        comparison_from: str | None = None,
        comparison_to: str | None = None,
        *,
        windows: DateWindows | None = None,
    ) -> dict[str, Any]:
        c_from, c_to, p_from, p_to = _windows_to_iso(
            windows, current_from, current_to, comparison_from, comparison_to
        )
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/evaluate/",
            json=self._window_body(c_from, c_to, p_from, p_to),
        )
        resp.raise_for_status()
        return resp.json()

    def investigate_tree(
        self,
        tree_id: str,
        current_from: str | None = None,
        current_to: str | None = None,
        comparison_from: str | None = None,
        comparison_to: str | None = None,
        *,
        windows: DateWindows | None = None,
        params: InvestigationParams | None = None,
        trend_periods: int | None = None,
        trend_grain: str | None = None,
        trend_as_of: str | None = None,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        metric: str | None = None,
        compare_trees: list[str] | None = None,
        max_depth: int | None = None,
        max_branching: int | None = None,
        max_segments: int | None = None,
        min_contribution_share: float | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Run a full server-side investigation bundle.

        If `progress_callback` is supplied, a daemon thread emits an
        `("awaiting_api", elapsed_seconds)` heartbeat every
        `_PROGRESS_INTERVAL_SECONDS` until the POST returns. The thread is
        torn down before the response is returned, regardless of outcome.
        """
        c_from, c_to, p_from, p_to = _windows_to_iso(
            windows, current_from, current_to, comparison_from, comparison_to
        )
        merged = _merge_investigation_params(
            params,
            trend_periods=trend_periods,
            trend_grain=trend_grain,
            trend_as_of=trend_as_of,
            segment_by=segment_by,
            filters=filters,
            metric=metric,
            compare_trees=compare_trees,
            max_depth=max_depth,
            max_branching=max_branching,
            max_segments=max_segments,
            min_contribution_share=min_contribution_share,
        )
        body = self._rca_body(c_from, c_to, p_from, p_to, **rca_params_to_kwargs(merged.as_rca()))
        body.update({
            "trend_periods": merged.trend_periods,
            "trend_grain": merged.trend_grain,
            "trend_as_of": merged.trend_as_of,
            "compare_trees": list(merged.compare_trees),
        })
        url = f"{self._base}/metric-trees/{tree_id}/investigate/"

        if progress_callback is None:
            resp = self._client.post(url, json=body, timeout=_INVESTIGATE_TIMEOUT)
        else:
            started = time.monotonic()
            done = threading.Event()

            def tick() -> None:
                while not done.wait(_PROGRESS_INTERVAL_SECONDS):
                    progress_callback("awaiting_api", time.monotonic() - started)

            heartbeat = threading.Thread(target=tick, daemon=True)
            heartbeat.start()
            try:
                resp = self._client.post(url, json=body, timeout=_INVESTIGATE_TIMEOUT)
            finally:
                done.set()

        resp.raise_for_status()
        return resp.json()

    def root_cause_tree(
        self,
        tree_id: str,
        current_from: str | None = None,
        current_to: str | None = None,
        comparison_from: str | None = None,
        comparison_to: str | None = None,
        *,
        windows: DateWindows | None = None,
        params: RcaParams | None = None,
        segment_by: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        metric: str | None = None,
        max_depth: int | None = None,
        max_branching: int | None = None,
        max_segments: int | None = None,
        min_contribution_share: float | None = None,
    ) -> RCAOutput:
        """Run RCA and return the enriched agent contract.

        The enriched contract — `schema_version`, `provenance`, materiality
        fields, normalized deltas — is part of the client's interface, not a
        post-processing step callers must remember.
        """
        c_from, c_to, p_from, p_to = _windows_to_iso(
            windows, current_from, current_to, comparison_from, comparison_to
        )
        merged = _merge_rca_params(
            params,
            segment_by=segment_by,
            filters=filters,
            metric=metric,
            max_depth=max_depth,
            max_branching=max_branching,
            max_segments=max_segments,
            min_contribution_share=min_contribution_share,
        )
        raw = self._root_cause_raw(
            tree_id, c_from, c_to, p_from, p_to, **rca_params_to_kwargs(merged),
        )
        return enrich_rca_output(raw, self._config)

    def _root_cause_raw(
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
        """Wire-level RCA call. Internal seam for tests; production callers
        go through `root_cause_tree`."""
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
        current_from: str | None = None,
        current_to: str | None = None,
        comparison_from: str | None = None,
        comparison_to: str | None = None,
        *,
        windows: DateWindows | None = None,
        params: ElasticityParams | None = None,
        outcome: str | None = None,
        lever: str | None = None,
        dimension: str | None = None,
        filters: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        c_from, c_to, p_from, p_to = _windows_to_iso(
            windows, current_from, current_to, comparison_from, comparison_to
        )
        merged_outcome = params.outcome if params else outcome
        merged_lever = params.lever if params else lever
        merged_dimension = params.dimension if params and dimension is None else dimension
        merged_filters = (
            dict(params.filters) if params and filters is None else (filters or {})
        )
        body = self._window_body(c_from, c_to, p_from, p_to)
        body.update({
            "outcome": merged_outcome,
            "lever": merged_lever,
            "dimension": merged_dimension,
            "filters": merged_filters,
        })
        if merged_dimension is None:
            body.pop("dimension")
        resp = self._client.post(
            f"{self._base}/metric-trees/{tree_id}/elasticity/",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()
