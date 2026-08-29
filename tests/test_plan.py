from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli
from qluent_cli.plan_contracts import PLAN_SCHEMA_VERSION


def _config(**overrides: Any) -> QluentConfig:
    defaults = dict(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )
    defaults.update(overrides)
    return QluentConfig(**defaults)


PLAN = {
    "nodes": [
        {"op": "source", "id": "src", "base": "orders"},
        {
            "op": "group_by",
            "id": "g",
            "input": "src",
            "dims": ["brand"],
            "metrics": ["gfv"],
        },
    ],
    "output": "g",
}

OK_RESPONSE = {
    "success": True,
    "schema_version": 1,
    "sql": "WITH src AS (SELECT 1) SELECT * FROM g",
    "rows": [
        {"brand": "acme", "gfv": 12.5},
        {"brand": "globex", "gfv": 9.0},
    ],
    "row_count": 2,
    "metadata": {
        "columns": ["brand", "gfv"],
        "grain": ["brand"],
        "metrics": {"gfv": {"kind": "sum", "summable": True}},
    },
    "plan_summary": {"bases": ["orders"], "metrics": ["gfv"]},
}

INVALID_RESPONSE = {
    "success": False,
    "error_code": "PLAN_INVALID",
    "error": "group_by.dims: unknown column 'brnd'; available ['brand', 'gfv_eur']",
}

CATALOG_RESPONSE = {
    "success": True,
    "schema_version": 1,
    "catalog": {
        "bases": {"orders": {"columns": ["brand", "gfv_eur"]}},
        "metrics": {"gfv": ["orders"]},
        "relationships": {},
        "derived_dimensions": ["order_month"],
    },
    "plan_schema": {"type": "object", "properties": {}},
}


class FakePlanClient:
    """Records calls; returns the canned payloads set on the class."""

    catalog_response: dict[str, Any] = {}
    plan_response: dict[str, Any] = {}
    calls: list[tuple[str, Any]] = []

    def __init__(self, config: QluentConfig) -> None:
        self.config = config

    def get_query_catalog(self) -> dict[str, Any]:
        type(self).calls.append(("get_query_catalog", None))
        return dict(type(self).catalog_response)

    def execute_plan(self, plan: dict[str, Any], *, progress_callback=None) -> dict[str, Any]:
        type(self).calls.append(("execute_plan", plan))
        return dict(type(self).plan_response)


def _wire(monkeypatch, config: QluentConfig | None = None) -> None:
    monkeypatch.setattr("qluent_cli.plan.load_config", lambda: config or _config())
    monkeypatch.setattr("qluent_cli.plan.QluentClient", FakePlanClient)
    FakePlanClient.calls = []


def test_catalog_renders_vocabulary(monkeypatch):
    FakePlanClient.catalog_response = dict(CATALOG_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["catalog"])

    assert result.exit_code == 0, result.output
    assert "orders: 2 columns" in result.output
    assert "gfv [orders]" in result.output
    assert "order_month" in result.output


def test_catalog_json_output_carries_plan_schema(monkeypatch):
    FakePlanClient.catalog_response = dict(CATALOG_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["catalog", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["contract_kind"] == "query_catalog"
    assert payload["plan_schema"] == {"type": "object", "properties": {}}
    assert payload["catalog"]["metrics"] == {"gfv": ["orders"]}


def test_catalog_missing_is_an_error(monkeypatch):
    FakePlanClient.catalog_response = {
        "success": False,
        "error_code": "QUERY_CATALOG_INVALID",
        "error": "The project has no loadable query_catalog",
    }
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["catalog"])

    assert result.exit_code != 0
    assert "QUERY_CATALOG_INVALID" in result.output


def test_plan_happy_path_renders_table_and_metadata(monkeypatch, isolated_config):
    FakePlanClient.plan_response = dict(OK_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN)])

    assert result.exit_code == 0, result.output
    assert "acme" in result.output
    assert "grain: brand" in result.output
    assert "SQL: WITH src" in result.output
    assert "run_id:" in result.output
    assert FakePlanClient.calls == [("execute_plan", PLAN)]


def test_plan_persists_run(monkeypatch, isolated_config):
    FakePlanClient.plan_response = dict(OK_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN)])
    assert result.exit_code == 0, result.output

    from qluent_cli import sessions

    record = sessions.find_last_run(command=sessions.PLAN_COMMAND)
    assert record is not None
    stored = record.load()
    assert stored["args"]["plan"] == PLAN
    assert stored["result"]["schema_version"] == PLAN_SCHEMA_VERSION
    assert stored["result"]["deterministic"] is True


def test_plan_from_file(monkeypatch, isolated_config, tmp_path):
    FakePlanClient.plan_response = dict(OK_RESPONSE)
    _wire(monkeypatch)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(PLAN))

    result = CliRunner().invoke(cli, ["plan", "--file", str(plan_file)])

    assert result.exit_code == 0, result.output
    assert FakePlanClient.calls == [("execute_plan", PLAN)]


def test_plan_invalid_is_a_repairable_zero_exit(monkeypatch):
    FakePlanClient.plan_response = dict(INVALID_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN)])

    assert result.exit_code == 0, result.output
    assert "Plan rejected" in result.output
    assert "unknown column 'brnd'" in result.output
    assert "re-run" in result.output


def test_plan_invalid_json_contract_marks_status(monkeypatch):
    FakePlanClient.plan_response = dict(INVALID_RESPONSE)
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN), "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "plan_invalid"
    assert payload["error_code"] == "PLAN_INVALID"


def test_plan_hard_error_raises(monkeypatch):
    FakePlanClient.plan_response = {
        "success": False,
        "error_code": "DATA_SOURCE_ERROR",
        "error": "Query execution failed.",
    }
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN)])

    assert result.exit_code != 0
    assert "DATA_SOURCE_ERROR" in result.output


def test_plan_catalog_invalid_is_a_hard_error_with_remediation(monkeypatch):
    FakePlanClient.plan_response = {
        "success": False,
        "error_code": "QUERY_CATALOG_INVALID",
        "error": "The project has no loadable query_catalog",
    }
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN)])

    assert result.exit_code != 0
    assert "QUERY_CATALOG_INVALID" in result.output
    assert "Model tab" in result.output
    # Never presented as something a corrected plan could fix.
    assert "Fix the plan" not in result.output


def test_plan_catalog_invalid_json_contract_is_status_error(monkeypatch):
    FakePlanClient.plan_response = {
        "success": False,
        "error_code": "QUERY_CATALOG_INVALID",
        "error": "The project has no loadable query_catalog",
    }
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", json.dumps(PLAN), "--json-output"])

    assert result.exit_code != 0
    assert "plan_invalid" not in result.output


def test_catalog_invalid_error_carries_remediation(monkeypatch):
    FakePlanClient.catalog_response = {
        "success": False,
        "error_code": "QUERY_CATALOG_INVALID",
        "error": "The project has no loadable query_catalog",
    }
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["catalog"])

    assert result.exit_code != 0
    assert "Model tab" in result.output


def test_plan_requires_exactly_one_input(monkeypatch, tmp_path):
    _wire(monkeypatch)

    neither = CliRunner().invoke(cli, ["plan"])
    assert neither.exit_code != 0
    assert "exactly one way" in neither.output

    plan_file = tmp_path / "plan.json"
    plan_file.write_text("{}")
    both = CliRunner().invoke(
        cli, ["plan", "{}", "--file", str(plan_file)]
    )
    assert both.exit_code != 0
    assert "exactly one way" in both.output


def test_plan_rejects_malformed_json(monkeypatch):
    _wire(monkeypatch)

    result = CliRunner().invoke(cli, ["plan", "{not json"])

    assert result.exit_code != 0
    assert "not valid JSON" in result.output
