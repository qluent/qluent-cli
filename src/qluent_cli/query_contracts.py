"""Stable JSON contract for ad-hoc natural-language queries.

Unlike the metric-tree contracts, these results come from the backend's LLM
workflow (NL -> SQL -> execution), so the contract is explicitly marked
non-deterministic. The builder is the single normalization seam for the two
wire shapes the backend emits:

- the sync ``POST /query/`` response (``explanation``, nested
  ``clarification: {message, questions}``), and
- the SSE terminal events from ``POST /query/stream`` (``result`` uses
  ``explanation`` but carries ``sql`` in a separate event; ``clarification``
  is flat ``{message, options}``; ``error`` is flat).
"""

from __future__ import annotations

from typing import Any, TypedDict

from qluent_cli.config import QluentConfig
from qluent_cli.contract_helpers import ProjectContext, Provenance


QUERY_SCHEMA_VERSION = "qluent.query.v1"

STATUS_OK = "ok"
STATUS_CLARIFICATION = "clarification_needed"
STATUS_ERROR = "error"


class QueryClarification(TypedDict):
    message: str
    options: list[str]


class QueryContract(TypedDict, total=False):
    schema_version: str
    contract_kind: str
    deterministic: bool
    status: str
    question: str | None
    answer: str | None
    sql: str | None
    columns: list[str] | None
    data: list[dict[str, Any]] | None
    row_count: int | None
    truncated: bool
    download_url: str | None
    google_sheets_url: str | None
    thread_id: str | None
    message_id: str | None
    plan: dict[str, Any] | None
    clarification: QueryClarification | None
    error_code: str | None
    error: str | None
    project_context: ProjectContext
    provenance: Provenance


def _normalize_clarification(
    raw: dict[str, Any], *, event: str | None
) -> QueryClarification | None:
    if event == "clarification":
        return {
            "message": str(raw.get("message") or ""),
            "options": list(raw.get("options") or []),
        }
    nested = raw.get("clarification")
    if isinstance(nested, dict):
        return {
            "message": str(nested.get("message") or ""),
            "options": list(nested.get("options") or nested.get("questions") or []),
        }
    return None


def _normalize_plan(raw: dict[str, Any]) -> dict[str, Any] | None:
    """The QueryPlan the backend compiled and executed for this question.

    Present only on ``plan_compile`` projects, and only on success. It is
    carried through verbatim — the same document ``qluent plan`` accepts — so
    an agent can review the plan behind an answer and re-run a corrected
    version deterministically. Anything that is not a JSON object is dropped
    rather than passed on as an unusable ``plan``.
    """
    plan = raw.get("plan")
    if plan is None:
        plan = raw.get("query_plan")
    return plan if isinstance(plan, dict) else None


def _derive_status(raw: dict[str, Any], clarification: QueryClarification | None) -> str:
    if raw.get("success"):
        return STATUS_OK
    if clarification is not None or raw.get("error_code") == "CLARIFICATION_NEEDED":
        return STATUS_CLARIFICATION
    return STATUS_ERROR


def build_query_contract(
    raw: dict[str, Any],
    config: QluentConfig,
    *,
    event: str | None = None,
    sql: str | None = None,
) -> QueryContract:
    """Normalize a query response (sync body or SSE terminal event payload).

    ``event`` is the SSE event name when the payload came off the stream
    (``result`` / ``clarification`` / ``error``); ``None`` means the sync
    response body. ``sql`` carries the stream's separate ``sql`` event, which
    wins over any inline field.
    """
    clarification = _normalize_clarification(raw, event=event)
    if event == "clarification":
        status = STATUS_CLARIFICATION
    elif event == "error":
        status = STATUS_ERROR
    elif event == "result":
        status = STATUS_OK if raw.get("success", True) else STATUS_ERROR
    else:
        status = _derive_status(raw, clarification)

    data = raw.get("data")
    row_count = raw.get("row_count")
    truncated = bool(
        isinstance(row_count, int) and isinstance(data, list) and row_count > len(data)
    )

    project_context: ProjectContext = {
        "project_uuid": config.project_uuid,
        "user_email": config.user_email,
        "api_url": config.api_url,
        "client_safe": config.client_safe,
    }
    prov: Provenance = {
        "source": "nl_query",
        "project_uuid": config.project_uuid,
    }

    return {
        "schema_version": QUERY_SCHEMA_VERSION,
        "contract_kind": "nl_query",
        "deterministic": False,
        "status": status,
        "question": raw.get("question"),
        "answer": raw.get("explanation") or raw.get("answer"),
        "sql": sql if sql is not None else raw.get("sql"),
        "columns": raw.get("columns"),
        "data": data,
        "row_count": row_count,
        "truncated": truncated,
        "download_url": raw.get("download_url"),
        "google_sheets_url": raw.get("google_sheets_url"),
        "thread_id": raw.get("thread_id"),
        "message_id": raw.get("message_id"),
        "plan": _normalize_plan(raw),
        "clarification": clarification,
        "error_code": raw.get("error_code"),
        "error": raw.get("error"),
        "project_context": project_context,
        "provenance": prov,
    }
