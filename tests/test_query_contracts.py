from __future__ import annotations

from qluent_cli.config import QluentConfig
from qluent_cli.query_contracts import (
    QUERY_SCHEMA_VERSION,
    STATUS_CLARIFICATION,
    STATUS_ERROR,
    STATUS_OK,
    build_query_contract,
)


CONFIG = QluentConfig(
    api_key="qk_test",
    api_url="https://api.example.com",
    project_uuid="project-123",
    user_email="user@example.com",
)


def test_sync_success_normalizes_explanation_to_answer():
    raw = {
        "success": True,
        "thread_id": "th_1",
        "message_id": "msg_1",
        "question": "top customers?",
        "sql": "SELECT 1",
        "explanation": "Here are the top customers.",
        "data": [{"customer": "Acme", "revenue": 100}],
        "columns": ["customer", "revenue"],
        "row_count": 1,
        "download_url": "https://example.com/dl",
    }

    contract = build_query_contract(raw, CONFIG)

    assert contract["schema_version"] == QUERY_SCHEMA_VERSION
    assert contract["contract_kind"] == "nl_query"
    assert contract["deterministic"] is False
    assert contract["status"] == STATUS_OK
    assert contract["answer"] == "Here are the top customers."
    assert contract["sql"] == "SELECT 1"
    assert contract["truncated"] is False
    assert contract["thread_id"] == "th_1"
    assert contract["project_context"]["project_uuid"] == "project-123"
    assert contract["provenance"]["source"] == "nl_query"


def test_sync_truncation_derived_from_row_count():
    raw = {
        "success": True,
        "thread_id": "th_1",
        "message_id": "msg_1",
        "question": "q",
        "data": [{"a": 1}, {"a": 2}],
        "columns": ["a"],
        "row_count": 5000,
    }

    contract = build_query_contract(raw, CONFIG)

    assert contract["truncated"] is True


def test_sync_clarification_normalizes_nested_questions_to_options():
    raw = {
        "success": False,
        "thread_id": "th_2",
        "message_id": "msg_2",
        "question": "revenue?",
        "clarification": {
            "message": "Which revenue do you mean?",
            "questions": ["Gross revenue", "Net revenue"],
        },
        "error_code": "CLARIFICATION_NEEDED",
    }

    contract = build_query_contract(raw, CONFIG)

    assert contract["status"] == STATUS_CLARIFICATION
    assert contract["clarification"] == {
        "message": "Which revenue do you mean?",
        "options": ["Gross revenue", "Net revenue"],
    }


def test_stream_result_event_merges_separate_sql_event():
    raw = {
        "success": True,
        "thread_id": "th_3",
        "message_id": "msg_3",
        "question": "q",
        "explanation": "Answer.",
        "data": [],
        "columns": [],
        "row_count": 0,
    }

    contract = build_query_contract(raw, CONFIG, event="result", sql="SELECT 2")

    assert contract["status"] == STATUS_OK
    assert contract["sql"] == "SELECT 2"
    assert contract["answer"] == "Answer."


def test_stream_clarification_event_uses_flat_options():
    raw = {
        "success": False,
        "thread_id": "th_4",
        "message_id": "msg_4",
        "question": "q",
        "message": "Need more detail.",
        "options": ["Option A", "Option B"],
    }

    contract = build_query_contract(raw, CONFIG, event="clarification")

    assert contract["status"] == STATUS_CLARIFICATION
    assert contract["clarification"] == {
        "message": "Need more detail.",
        "options": ["Option A", "Option B"],
    }
    assert contract["thread_id"] == "th_4"


def test_stream_error_event_maps_to_error_status():
    raw = {"success": False, "error_code": "EXECUTION_ERROR", "error": "boom"}

    contract = build_query_contract(raw, CONFIG, event="error")

    assert contract["status"] == STATUS_ERROR
    assert contract["error_code"] == "EXECUTION_ERROR"
    assert contract["error"] == "boom"
