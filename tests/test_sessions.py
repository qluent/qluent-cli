from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from qluent_cli import sessions
from qluent_cli.config import QluentConfig
from qluent_cli.main import cli


# -------------------------- pure-function tests --------------------------


def test_generate_run_id_is_well_formed():
    run_id = sessions.generate_run_id()
    assert sessions.is_valid_run_id(run_id)
    assert len(run_id) == 16


def test_generate_run_id_is_time_sortable():
    earlier = sessions.generate_run_id(now_ms=1_700_000_000_000)
    later = sessions.generate_run_id(now_ms=1_700_000_001_000)
    assert earlier < later


def test_parse_relative_seconds_short_forms():
    assert sessions.parse_relative_seconds("30d") == 30 * 86400
    assert sessions.parse_relative_seconds("12h") == 12 * 3600
    assert sessions.parse_relative_seconds("2w") == 14 * 86400


def test_parse_relative_seconds_natural_form():
    assert sessions.parse_relative_seconds("7 days ago") == 7 * 86400
    assert sessions.parse_relative_seconds("1 hour") == 3600


def test_parse_relative_seconds_rejects_garbage():
    with pytest.raises(ValueError):
        sessions.parse_relative_seconds("yesterday")


# -------------------------- record / retrieve --------------------------


def _record(
    *,
    command: str = sessions.INVESTIGATE_COMMAND,
    tree_id: str | None = "revenue",
    payload: dict | None = None,
    profile: str = "ludvig@qluent.com@https://api.example.com",
    period_start: str | None = "2026-04-21",
    period_end: str | None = "2026-04-27",
    comparison_start: str | None = "2026-04-14",
    comparison_end: str | None = "2026-04-20",
    args: dict | None = None,
    client_safe: bool = True,
) -> sessions.RunRecord:
    return sessions.record_run(
        command=command,
        tree_id=tree_id,
        period_start=period_start,
        period_end=period_end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        profile=profile,
        client_safe=client_safe,
        args=args or {},
        payload=payload or {"tree_id": tree_id, "agent": {}},
    )


def test_record_run_writes_file_and_indexes(isolated_config):
    record = _record(payload={"tree_id": "revenue", "delta": 10})

    assert record.path.exists()
    fetched = sessions.get_run(record.run_id)
    assert fetched is not None
    assert fetched.run_id == record.run_id
    assert fetched.tree_id == "revenue"
    assert fetched.client_safe is True
    body = json.loads(record.path.read_text())
    assert body["run_id"] == record.run_id
    assert body["result"] == {"tree_id": "revenue", "delta": 10}


def test_record_run_sanitizes_tree_id_for_filename(isolated_config):
    record = _record(tree_id="../sales/revenue", payload={"tree_id": "../sales/revenue"})

    assert record.tree_id == "../sales/revenue"
    assert record.path.name.endswith(f"-{record.run_id}.json")
    assert record.path.name.startswith("sales_revenue-")
    assert record.path.parent == isolated_config[0] / "sessions" / record.started_at[:4] / record.started_at[5:7] / record.started_at[8:10]
    body = json.loads(record.path.read_text())
    assert body["tree_id"] == "../sales/revenue"


def test_get_run_returns_none_when_missing(isolated_config):
    assert sessions.get_run("01234567ABCDEFGH") is None


def test_find_last_run_filters_by_command_and_tree(isolated_config):
    inv_revenue = _record(command=sessions.INVESTIGATE_COMMAND, tree_id="revenue")
    time.sleep(0.005)
    _record(command=sessions.INVESTIGATE_COMMAND, tree_id="growth")
    time.sleep(0.005)
    deep = _record(command=sessions.DEEP_DIVE_COMMAND, tree_id=None)

    last_inv_revenue = sessions.find_last_run(
        command=sessions.INVESTIGATE_COMMAND, tree_id="revenue"
    )
    assert last_inv_revenue is not None
    assert last_inv_revenue.run_id == inv_revenue.run_id

    last_deep = sessions.find_last_run(command=sessions.DEEP_DIVE_COMMAND)
    assert last_deep is not None
    assert last_deep.run_id == deep.run_id


def test_list_runs_filters_and_orders(isolated_config):
    a = _record(tree_id="revenue")
    time.sleep(0.005)
    b = _record(tree_id="growth")
    time.sleep(0.005)
    c = _record(tree_id="revenue")

    all_runs = sessions.list_runs()
    assert [r.run_id for r in all_runs] == [c.run_id, b.run_id, a.run_id]

    revenue_runs = sessions.list_runs(tree_id="revenue")
    assert {r.run_id for r in revenue_runs} == {a.run_id, c.run_id}

    capped = sessions.list_runs(limit=1)
    assert len(capped) == 1


def test_list_runs_since_filters(isolated_config):
    old = _record(tree_id="revenue")
    cutoff_iso = sessions._iso(datetime.now(timezone.utc) - timedelta(days=10))
    with sessions._connect() as conn:
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            (cutoff_iso, old.run_id),
        )
    fresh = _record(tree_id="growth")

    recent = sessions.list_runs(since="3d")
    assert [r.run_id for r in recent] == [fresh.run_id]


def test_prune_older_than_removes_old_runs(isolated_config):
    old = _record(tree_id="revenue")
    cutoff_iso = sessions._iso(datetime.now(timezone.utc) - timedelta(days=10))
    with sessions._connect() as conn:
        conn.execute(
            "UPDATE runs SET started_at = ? WHERE run_id = ?",
            (cutoff_iso, old.run_id),
        )
    fresh = _record(tree_id="growth")

    removed = sessions.prune_runs(older_than="3d")
    assert [r.run_id for r in removed] == [old.run_id]
    assert sessions.get_run(old.run_id) is None
    assert not old.path.exists()
    assert sessions.get_run(fresh.run_id) is not None


def test_prune_max_runs_keeps_most_recent(isolated_config):
    a = _record(tree_id="revenue")
    time.sleep(0.005)
    b = _record(tree_id="revenue")
    time.sleep(0.005)
    c = _record(tree_id="revenue")

    removed = sessions.prune_runs(max_runs=2)
    removed_ids = {r.run_id for r in removed}
    assert removed_ids == {a.run_id}
    assert sessions.get_run(a.run_id) is None
    assert sessions.get_run(b.run_id) is not None
    assert sessions.get_run(c.run_id) is not None


# -------------------------- CLI integration --------------------------


def _stub_config(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.trees.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
            client_safe=False,
        ),
    )


def test_runs_list_empty_says_so(isolated_config):
    result = CliRunner().invoke(cli, ["runs", "list"])
    assert result.exit_code == 0
    assert "No persisted runs." in result.output


def test_runs_list_filters_by_tree(isolated_config):
    _record(tree_id="revenue")
    time.sleep(0.005)
    _record(tree_id="growth")

    result = CliRunner().invoke(cli, ["runs", "list", "--tree", "revenue", "--json-output"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["tree_id"] == "revenue"


def test_runs_show_by_id(isolated_config):
    record = _record(payload={"tree_id": "revenue", "delta": 5})
    result = CliRunner().invoke(cli, ["runs", "show", record.run_id, "--json-output"])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["result"] == {"tree_id": "revenue", "delta": 5}


def test_runs_show_last(isolated_config):
    _record(tree_id="revenue", payload={"tag": "older"})
    time.sleep(0.005)
    newer = _record(tree_id="revenue", payload={"tag": "newer"})

    result = CliRunner().invoke(
        cli,
        ["runs", "show", "--last", "--tree", "revenue", "--json-output"],
    )
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["run_id"] == newer.run_id
    assert body["result"]["tag"] == "newer"


def test_runs_show_requires_run_id_or_last(isolated_config):
    result = CliRunner().invoke(cli, ["runs", "show"])
    assert result.exit_code != 0
    assert "Provide a RUN_ID or use --last" in result.output


def test_runs_prune_requires_at_least_one_flag(isolated_config):
    result = CliRunner().invoke(cli, ["runs", "prune"])
    assert result.exit_code != 0
    assert "Provide --older-than" in result.output


def test_investigate_persists_run_and_resumable(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.list_trees",
        lambda self: {"trees": [{"id": "revenue", "nodes": []}]},
    )

    api_calls: list[str] = []

    def mock_investigate(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        api_calls.append(tree_id)
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "agent": {"top_findings": ["grew 10%"]},
        }

    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.investigate_tree", mock_investigate
    )

    runner = CliRunner()
    first = runner.invoke(
        cli,
        [
            "trees",
            "investigate",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--json-output",
        ],
    )
    assert first.exit_code == 0, first.output
    assert len(api_calls) == 1

    records = sessions.list_runs(
        tree_id="revenue", command=sessions.INVESTIGATE_COMMAND
    )
    assert len(records) == 1
    run_id = records[0].run_id

    resumed = runner.invoke(
        cli,
        ["trees", "investigate", "revenue", "--resume", run_id, "--json-output"],
    )
    assert resumed.exit_code == 0, resumed.output
    assert len(api_calls) == 1  # cache hit, no new API call
    payload = json.loads(resumed.output)
    assert payload["tree_id"] == "revenue"

    last = runner.invoke(
        cli,
        ["trees", "investigate", "revenue", "--last", "--json-output"],
    )
    assert last.exit_code == 0, last.output
    assert len(api_calls) == 1


def test_investigate_stream_completion_run_id_is_resumable(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.list_trees",
        lambda self: {"trees": [{"id": "revenue", "nodes": []}]},
    )

    api_calls: list[str] = []

    def mock_investigate(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        api_calls.append(tree_id)
        return {
            "tree_id": tree_id,
            "tree_label": "Revenue",
            "agent": {"top_findings": ["grew 10%"]},
        }

    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.investigate_tree", mock_investigate
    )

    runner = CliRunner()
    streamed = runner.invoke(
        cli,
        [
            "trees",
            "investigate",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--json-output",
            "--stream",
        ],
    )
    assert streamed.exit_code == 0, streamed.output
    events = [json.loads(line) for line in streamed.output.splitlines()]
    completed = events[-1]
    assert completed["type"] == "run.completed"

    resumed = runner.invoke(
        cli,
        [
            "trees",
            "investigate",
            "revenue",
            "--resume",
            completed["run_id"],
            "--json-output",
        ],
    )
    assert resumed.exit_code == 0, resumed.output
    assert len(api_calls) == 1
    assert json.loads(resumed.output)["tree_id"] == "revenue"


def test_investigate_failure_does_not_persist(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.list_trees",
        lambda self: {"trees": [{"id": "revenue", "nodes": []}]},
    )

    def boom(self, tree_id, c_from, c_to, p_from, p_to, **kwargs):
        raise RuntimeError("server down")

    monkeypatch.setattr("qluent_cli.trees.QluentClient.investigate_tree", boom)

    result = CliRunner().invoke(
        cli,
        [
            "trees",
            "investigate",
            "revenue",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--json-output",
        ],
    )
    assert result.exit_code != 0
    assert sessions.list_runs() == []


def test_investigate_resume_rejects_wrong_tree(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    record = _record(tree_id="revenue", command=sessions.INVESTIGATE_COMMAND)

    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.list_trees",
        lambda self: {"trees": [{"id": "growth", "nodes": []}]},
    )

    result = CliRunner().invoke(
        cli,
        ["trees", "investigate", "growth", "--resume", record.run_id, "--json-output"],
    )
    assert result.exit_code != 0
    assert "is for tree 'revenue'" in result.output


def test_investigate_last_with_no_runs_errors(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    result = CliRunner().invoke(
        cli, ["trees", "investigate", "revenue", "--last", "--json-output"]
    )
    assert result.exit_code != 0
    assert "No prior 'trees investigate' run" in result.output


def test_deep_dive_persists_run(isolated_config, monkeypatch):
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.list_trees",
        lambda self: {
            "trees": [
                {"id": "revenue", "nodes": []},
                {"id": "growth", "nodes": []},
            ]
        },
    )

    def mock_investigate(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        return {"tree_id": tree_id, "agent": {}}

    monkeypatch.setattr(
        "qluent_cli.trees.QluentClient.investigate_tree", mock_investigate
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "trees",
            "deep-dive",
            "--current",
            "2026-03-09:2026-03-15",
            "--compare",
            "2026-03-02:2026-03-08",
            "--json-output",
        ],
    )
    assert result.exit_code == 0, result.output
    records = sessions.list_runs(command=sessions.DEEP_DIVE_COMMAND)
    assert len(records) == 1
    assert records[0].tree_id is None

    resumed = runner.invoke(
        cli,
        ["trees", "deep-dive", "--last", "--json-output"],
    )
    assert resumed.exit_code == 0, resumed.output
    payload = json.loads(resumed.output)
    assert set(payload["trees"].keys()) == {"revenue", "growth"}
