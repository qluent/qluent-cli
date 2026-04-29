"""Tests for the RunManager (issue #77).

The investigation flow today is split across `trees.py` (Click command),
`runs.py` (RunReporter + run_investigation), and `sessions.py` (persistence).
RunManager owns the lifecycle so adapters say "investigate this tree" and
get back a finished, persisted result.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from qluent_cli.client_configs import InvestigationParams
from qluent_cli.config import QluentConfig
from qluent_cli.dates import DateWindow, DateWindows
from qluent_cli.run_manager import RunManager, RunResult


def _config() -> QluentConfig:
    return QluentConfig(
        api_key="qk_test",
        api_url="https://api.example.com",
        project_uuid="project-123",
        user_email="user@example.com",
    )


def _windows() -> DateWindows:
    return DateWindows(
        current=DateWindow(date(2026, 3, 9), date(2026, 3, 15)),
        comparison=DateWindow(date(2026, 3, 2), date(2026, 3, 8)),
    )


class _FakeClient:
    """Minimal client double satisfying RunManager's needs."""

    def __init__(self, bundle: dict[str, Any] | None = None) -> None:
        self.bundle = bundle or {
            "tree_id": "growth",
            "agent": {"recommended_next_steps": []},
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_trees(self) -> dict[str, Any]:
        self.calls.append(("list_trees", {}))
        return {"trees": [{"id": "growth", "nodes": [{"id": "users"}]}]}

    def investigate_tree(self, tree_id, **kwargs):
        self.calls.append(("investigate_tree", {"tree_id": tree_id, **kwargs}))
        return dict(self.bundle)


def test_run_manager_investigate_returns_bundle_without_run_id_when_not_persisted():
    client = _FakeClient()
    manager = RunManager(client, _config(), persist=False)

    result = manager.investigate(
        "growth",
        windows=_windows(),
        params=InvestigationParams(),
    )

    assert isinstance(result, RunResult)
    assert result.run_id is None
    assert result.bundle["tree_id"] == "growth"
    assert result.from_cache is False


def test_run_manager_passes_windows_and_params_to_client():
    client = _FakeClient()
    manager = RunManager(client, _config(), persist=False)
    params = InvestigationParams(max_depth=4, segment_by=("region",))

    manager.investigate("growth", windows=_windows(), params=params)

    investigate_call = next(c for c in client.calls if c[0] == "investigate_tree")
    kwargs = investigate_call[1]
    assert kwargs["windows"].iso_tuple() == (
        "2026-03-09",
        "2026-03-15",
        "2026-03-02",
        "2026-03-08",
    )
    assert kwargs["params"] is params


def test_run_manager_sanitizes_agent_next_steps():
    """Sanitization (drop next-steps targeting non-tree ids) is part of the
    contract — every adapter gets sanitized output, not raw."""
    client = _FakeClient(
        bundle={
            "tree_id": "growth",
            "agent": {
                "recommended_next_steps": [
                    {
                        "command": "qluent trees compare growth nonexistent_tree",
                        "why": "compare these.",
                    }
                ]
            },
        }
    )
    manager = RunManager(client, _config(), persist=False)
    result = manager.investigate("growth", windows=_windows(), params=InvestigationParams())
    step = result.bundle["agent"]["recommended_next_steps"][0]
    assert "command" not in step  # invalid target was scrubbed


def test_run_manager_persists_when_persist_true(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_record_run(**kwargs):
        captured.update(kwargs)
        from pathlib import Path

        from qluent_cli.sessions import RunRecord

        return RunRecord(
            run_id="ABCDEF1234567890",
            command=kwargs["command"],
            tree_id=kwargs["tree_id"],
            period_start=kwargs["period_start"],
            period_end=kwargs["period_end"],
            comparison_start=kwargs["comparison_start"],
            comparison_end=kwargs["comparison_end"],
            started_at="2026-03-09T00:00:00Z",
            profile=kwargs.get("profile"),
            client_safe=kwargs.get("client_safe", False),
            path=Path("/tmp/run.json"),
        )

    monkeypatch.setattr("qluent_cli.run_manager.sessions.record_run", fake_record_run)

    client = _FakeClient()
    manager = RunManager(client, _config(), persist=True)
    result = manager.investigate("growth", windows=_windows(), params=InvestigationParams())

    assert captured["tree_id"] == "growth"
    assert captured["period_start"] == "2026-03-09"
    assert captured["comparison_end"] == "2026-03-08"
    # run_id from the persisted record propagates back to the result.
    assert result.run_id == "ABCDEF1234567890"


def test_run_manager_continues_when_persist_fails(monkeypatch, capsys):
    """Persist failure must not lose the result. The bundle still flows back;
    a warning goes to stderr."""

    def boom(**_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("qluent_cli.run_manager.sessions.record_run", boom)

    client = _FakeClient()
    manager = RunManager(client, _config(), persist=True)
    result = manager.investigate("growth", windows=_windows(), params=InvestigationParams())

    # bundle still flows through
    assert result.bundle["tree_id"] == "growth"
    assert result.run_id is None
    err = capsys.readouterr().err
    assert "failed to persist run" in err.lower()


def test_run_manager_does_not_persist_when_disabled(monkeypatch):
    called = {"n": 0}

    def fake_record_run(**_kwargs):
        called["n"] += 1
        raise AssertionError("should not be called when persist=False")

    monkeypatch.setattr("qluent_cli.run_manager.sessions.record_run", fake_record_run)

    client = _FakeClient()
    manager = RunManager(client, _config(), persist=False)
    manager.investigate("growth", windows=_windows(), params=InvestigationParams())

    assert called["n"] == 0
