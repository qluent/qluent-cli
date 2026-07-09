"""Stable JSON contracts for the composable query-plan commands.

Unlike ``qluent query`` (the backend's LLM workflow, marked non-deterministic),
a QueryPlan compiles deterministically against the project's closed-world
catalog: the same plan always produces the same SQL, and a plan the compiler
rejects comes back as a *repairable* error the caller fixes and resubmits.
The contracts mark that provenance so downstream consumers (plugin skills,
agents) can treat plan results as deterministic evidence.
"""

from __future__ import annotations

from typing import Any, TypedDict

from qluent_cli.config import QluentConfig
from qluent_cli.contract_helpers import ProjectContext, Provenance

PLAN_SCHEMA_VERSION = "qluent.plan.v1"
CATALOG_SCHEMA_VERSION = "qluent.catalog.v1"

STATUS_OK = "ok"
# The compiler (or scope guard) rejected the plan with a repairable message —
# fix the plan and re-run. Deliberately distinct from STATUS_ERROR so agents
# know retrying with the same plan is pointless but a *corrected* plan is not.
STATUS_PLAN_INVALID = "plan_invalid"
STATUS_ERROR = "error"

_REPAIRABLE_ERROR_CODES = frozenset(
    {"PLAN_INVALID", "PLAN_SCOPE_VIOLATION", "QUERY_CATALOG_INVALID"}
)


class PlanContract(TypedDict, total=False):
    schema_version: str
    contract_kind: str
    deterministic: bool
    status: str
    sql: str | None
    columns: list[str] | None
    data: list[dict[str, Any]] | None
    row_count: int | None
    grain: list[str] | None
    metrics: dict[str, Any] | None
    plan_summary: dict[str, Any] | None
    error_code: str | None
    error: str | None
    project_context: ProjectContext
    provenance: Provenance


class CatalogContract(TypedDict, total=False):
    schema_version: str
    contract_kind: str
    status: str
    catalog: dict[str, Any] | None
    plan_schema: dict[str, Any] | None
    error_code: str | None
    error: str | None
    project_context: ProjectContext
    provenance: Provenance


def _project_context(config: QluentConfig) -> ProjectContext:
    return {
        "project_uuid": config.project_uuid,
        "user_email": config.user_email,
        "api_url": config.api_url,
        "client_safe": config.client_safe,
    }


def _derive_status(raw: dict[str, Any]) -> str:
    if raw.get("success"):
        return STATUS_OK
    if raw.get("error_code") in _REPAIRABLE_ERROR_CODES:
        return STATUS_PLAN_INVALID
    return STATUS_ERROR


def build_plan_contract(raw: dict[str, Any], config: QluentConfig) -> PlanContract:
    """Normalize a query-plan response (success body or 422 error body)."""
    metadata = raw.get("metadata") or {}
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "contract_kind": "query_plan",
        "deterministic": True,
        "status": _derive_status(raw),
        "sql": raw.get("sql"),
        "columns": metadata.get("columns"),
        "data": raw.get("rows"),
        "row_count": raw.get("row_count"),
        "grain": metadata.get("grain"),
        "metrics": metadata.get("metrics"),
        "plan_summary": raw.get("plan_summary"),
        "error_code": raw.get("error_code"),
        "error": raw.get("error"),
        "project_context": _project_context(config),
        "provenance": {
            "source": "query_plan",
            "project_uuid": config.project_uuid,
        },
    }


def build_catalog_contract(
    raw: dict[str, Any], config: QluentConfig
) -> CatalogContract:
    """Normalize a query-catalog response (success body or 422 error body)."""
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "contract_kind": "query_catalog",
        "status": STATUS_OK if raw.get("success") else STATUS_ERROR,
        "catalog": raw.get("catalog"),
        "plan_schema": raw.get("plan_schema"),
        "error_code": raw.get("error_code"),
        "error": raw.get("error"),
        "project_context": _project_context(config),
        "provenance": {
            "source": "query_catalog",
            "project_uuid": config.project_uuid,
        },
    }
