"""Tests for the run-lifecycle module — exercise the seam directly, no CliRunner."""

from __future__ import annotations

from typing import Any

from qluent_cli.runs import (
    RunReporter,
    collect_tree_metadata,
    run_investigation,
    sanitize_recommended_next_steps,
)


TREE_DATA: dict[str, Any] = {
    "trees": [
        {
            "id": "revenue",
            "label": "Revenue",
            "nodes": [
                {"id": "net_revenue"},
                {"id": "orders"},
                {"node_id": "aov"},
            ],
        },
        {
            "id": "growth",
            "nodes": [{"id": "signups"}],
        },
        {
            # Trees with no id are skipped
            "label": "Orphan",
            "nodes": [{"id": "noise"}],
        },
    ]
}


class _FakeClient:
    def __init__(self, bundle):
        self._bundle = bundle
        self.investigate_calls: list[dict[str, Any]] = []
        self.list_calls: int = 0

    def list_trees(self) -> dict[str, Any]:
        self.list_calls += 1
        return TREE_DATA

    def investigate_tree(self, tree_id, c_from, c_to, p_from, p_to, **kwargs):
        self.investigate_calls.append(
            {
                "tree_id": tree_id,
                "current_from": c_from,
                "current_to": c_to,
                "comparison_from": p_from,
                "comparison_to": p_to,
                **kwargs,
            }
        )
        return dict(self._bundle)


# ---------------------------------------------------------------------------
# collect_tree_metadata
# ---------------------------------------------------------------------------


def test_collect_tree_metadata_indexes_trees_and_metrics():
    tree_ids, metrics_by_tree = collect_tree_metadata(TREE_DATA)
    assert tree_ids == {"revenue", "growth"}
    assert metrics_by_tree["revenue"] == {"net_revenue", "orders", "aov"}
    assert metrics_by_tree["growth"] == {"signups"}


def test_collect_tree_metadata_handles_empty_payload():
    assert collect_tree_metadata({}) == (set(), {})
    assert collect_tree_metadata({"trees": []}) == (set(), {})


# ---------------------------------------------------------------------------
# sanitize_recommended_next_steps
# ---------------------------------------------------------------------------


def test_sanitize_rewrites_metric_compare_into_rca_analyze():
    bundle = {
        "tree_id": "revenue",
        "agent": {
            "recommended_next_steps": [
                {
                    "command": "qluent trees compare revenue orders --period 'last 7 days'",
                    "why": "Compare a metric.",
                }
            ]
        },
    }
    sanitize_recommended_next_steps(
        bundle,
        available_tree_ids={"revenue"},
        metrics_by_tree={"revenue": {"orders"}},
    )
    step = bundle["agent"]["recommended_next_steps"][0]
    assert step["command"].startswith(
        "qluent rca analyze revenue --metric orders"
    )
    assert "Converted from compare" in step["why"]


def test_sanitize_strips_unknown_compare_targets():
    bundle = {
        "tree_id": "revenue",
        "agent": {
            "recommended_next_steps": [
                {"command": "qluent trees compare revenue ghost"}
            ]
        },
    }
    sanitize_recommended_next_steps(
        bundle,
        available_tree_ids={"revenue"},
        metrics_by_tree={"revenue": set()},
    )
    step = bundle["agent"]["recommended_next_steps"][0]
    assert "command" not in step
    assert "must be available tree ids" in step["why"]


def test_sanitize_drops_malformed_command():
    bundle = {
        "agent": {
            "recommended_next_steps": [{"command": "qluent trees compare 'unterminated"}]
        },
    }
    sanitize_recommended_next_steps(
        bundle, available_tree_ids={"revenue"}, metrics_by_tree={"revenue": set()}
    )
    step = bundle["agent"]["recommended_next_steps"][0]
    assert "command" not in step


def test_sanitize_no_op_when_agent_section_missing():
    bundle = {"tree_id": "revenue"}
    sanitize_recommended_next_steps(
        bundle, available_tree_ids={"revenue"}, metrics_by_tree={"revenue": set()}
    )
    assert bundle == {"tree_id": "revenue"}


# ---------------------------------------------------------------------------
# run_investigation
# ---------------------------------------------------------------------------


def test_run_investigation_passes_kwargs_through_and_sanitizes():
    bundle_template = {
        "tree_id": "revenue",
        "agent": {
            "recommended_next_steps": [
                {
                    "command": "qluent trees compare revenue orders",
                    "why": "metric compare suggested",
                }
            ]
        },
    }
    client = _FakeClient(bundle_template)
    bundle = run_investigation(
        client,
        tree_id="revenue",
        current_from="2026-04-01",
        current_to="2026-04-07",
        comparison_from="2026-03-25",
        comparison_to="2026-03-31",
        max_depth=2,
        max_branching=3,
    )
    assert client.list_calls == 1
    assert client.investigate_calls[0]["max_depth"] == 2
    assert client.investigate_calls[0]["max_branching"] == 3
    step = bundle["agent"]["recommended_next_steps"][0]
    assert step["command"].startswith("qluent rca analyze revenue --metric orders")


def test_run_investigation_skips_list_trees_when_trees_data_provided():
    client = _FakeClient({"tree_id": "revenue"})
    run_investigation(
        client,
        tree_id="revenue",
        current_from="2026-04-01",
        current_to="2026-04-07",
        comparison_from="2026-03-25",
        comparison_to="2026-03-31",
        trees_data=TREE_DATA,
    )
    assert client.list_calls == 0
    assert len(client.investigate_calls) == 1


# ---------------------------------------------------------------------------
# RunReporter
# ---------------------------------------------------------------------------


def test_run_reporter_emits_jsonl_when_streaming(capsys):
    reporter = RunReporter(
        command="investigate",
        stream=True,
        tree_id="revenue",
        period_label="last 7 days",
    )
    reporter.start()
    reporter.progress("awaiting_api", elapsed=1.5)
    reporter.complete({"tree_id": "revenue"})
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert len(out_lines) == 3
    import json
    started, progress, completed = (json.loads(line) for line in out_lines)
    assert started["type"] == "run.started"
    assert started["command"] == "investigate"
    assert progress["type"] == "run.progress"
    assert progress["stage"] == "awaiting_api"
    assert completed["type"] == "run.completed"
    assert completed["result"] == {"tree_id": "revenue"}


def test_run_reporter_uses_stderr_when_not_streaming(capsys):
    reporter = RunReporter(
        command="investigate",
        stream=False,
        tree_id="revenue",
        period_label="last 7 days",
    )
    reporter.start()
    reporter.progress("awaiting_api", elapsed=2.0)
    captured = capsys.readouterr()
    # JSONL only goes to stdout when streaming; non-streaming uses stderr
    assert captured.out == ""
    assert "[qluent] investigate revenue" in captured.err
    assert "awaiting response" in captured.err
