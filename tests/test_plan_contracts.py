from __future__ import annotations

from typing import Any

from qluent_cli.config import QluentConfig
from qluent_cli.plan_contracts import (
    CATALOG_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PLAN_INVALID,
    build_catalog_contract,
    build_plan_contract,
)

CONFIG = QluentConfig(
    api_key="qk_test",
    api_url="https://api.example.com",
    project_uuid="project-123",
    user_email="user@example.com",
)


def _ok_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "schema_version": 1,
        "sql": "WITH g AS (SELECT 1) SELECT * FROM g",
        "rows": [{"brand": "acme", "gfv": 1.0}],
        "row_count": 1,
        "metadata": {
            "columns": ["brand", "gfv"],
            "grain": ["brand"],
            "metrics": {"gfv": {"kind": "sum", "summable": True}},
        },
        "plan_summary": {"bases": ["orders"]},
    }
    payload.update(overrides)
    return payload


def test_plan_contract_marks_deterministic_provenance():
    contract = build_plan_contract(_ok_payload(), CONFIG)

    assert contract["schema_version"] == PLAN_SCHEMA_VERSION
    assert contract["contract_kind"] == "query_plan"
    assert contract["deterministic"] is True
    assert contract["status"] == STATUS_OK
    assert contract["columns"] == ["brand", "gfv"]
    assert contract["grain"] == ["brand"]
    assert contract["metrics"]["gfv"]["summable"] is True
    assert contract["data"] == [{"brand": "acme", "gfv": 1.0}]
    assert contract["provenance"] == {
        "source": "query_plan",
        "project_uuid": "project-123",
    }


def test_plan_contract_repairable_codes_map_to_plan_invalid():
    for code in ("PLAN_INVALID", "PLAN_SCOPE_VIOLATION", "QUERY_CATALOG_INVALID"):
        contract = build_plan_contract(
            {"success": False, "error_code": code, "error": "fix me"}, CONFIG
        )
        assert contract["status"] == STATUS_PLAN_INVALID
        assert contract["error"] == "fix me"


def test_plan_contract_other_failures_are_errors():
    contract = build_plan_contract(
        {"success": False, "error_code": "DATA_SOURCE_ERROR", "error": "boom"},
        CONFIG,
    )
    assert contract["status"] == STATUS_ERROR


def test_catalog_contract_passthrough():
    contract = build_catalog_contract(
        {
            "success": True,
            "catalog": {"bases": {"orders": {"columns": ["brand"]}}},
            "plan_schema": {"type": "object"},
        },
        CONFIG,
    )
    assert contract["schema_version"] == CATALOG_SCHEMA_VERSION
    assert contract["status"] == STATUS_OK
    assert contract["catalog"]["bases"] == {"orders": {"columns": ["brand"]}}
    assert contract["plan_schema"] == {"type": "object"}
    assert contract["provenance"]["source"] == "query_catalog"
