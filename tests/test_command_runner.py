"""Tests for the command-runner decorator (issue #81).

After the prior deepenings (rendering, window resolver, client configs,
RunManager), every Click command still has the same skeleton:

    config = load_config()
    client = QluentClient(config)
    try:
        ... business logic returning a Result ...
    except PeriodResolutionError as exc:
        raise click.ClickException(str(exc))
    render(result, as_json=as_json)

The capstone collapses that skeleton into a decorator.  Business code
returns a `Result`; the decorator handles config/client injection,
error mapping, and rendering.
"""

from __future__ import annotations

import json

import click
from click.testing import CliRunner

from qluent_cli.command_runner import qluent_command
from qluent_cli.config import QluentConfig
from qluent_cli.rendering import Result, simple_result
from qluent_cli.window_resolver import PeriodResolutionError


def _stub_config(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.command_runner.load_config",
        lambda: QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )


class _FakeClient:
    def __init__(self, config) -> None:
        self.config = config

    def list_trees(self) -> dict:
        return {"trees": [{"id": "growth"}]}


def _stub_client(monkeypatch):
    monkeypatch.setattr("qluent_cli.command_runner.QluentClient", _FakeClient)


def test_qluent_command_injects_client_and_config_and_renders(monkeypatch):
    _stub_config(monkeypatch)
    _stub_client(monkeypatch)

    @click.command()
    @click.option("--json-output", "as_json", is_flag=True)
    @qluent_command
    def my_cmd(client, config, *, as_json):
        assert isinstance(config, QluentConfig)
        return simple_result(client.list_trees(), formatter=lambda d: f"trees: {len(d['trees'])}")

    out = CliRunner().invoke(my_cmd, []).output.strip()
    assert out == "trees: 1"


def test_qluent_command_emits_json_when_flag_set(monkeypatch):
    _stub_config(monkeypatch)
    _stub_client(monkeypatch)

    @click.command()
    @click.option("--json-output", "as_json", is_flag=True)
    @qluent_command
    def my_cmd(client, config, *, as_json):
        return Result(json_payload={"ok": True}, human="HUMAN")

    out = CliRunner().invoke(my_cmd, ["--json-output"]).output
    assert json.loads(out) == {"ok": True}


def test_qluent_command_maps_period_resolution_error_to_click_exception(monkeypatch):
    _stub_config(monkeypatch)
    _stub_client(monkeypatch)

    @click.command()
    @click.option("--json-output", "as_json", is_flag=True)
    @qluent_command
    def my_cmd(client, config, *, as_json):
        raise PeriodResolutionError("Run XXX is for tree 'growth', not 'revenue'.")

    result = CliRunner().invoke(my_cmd, [])
    assert result.exit_code != 0
    assert "Run XXX is for tree 'growth'" in result.output


def test_qluent_command_passes_through_user_click_options(monkeypatch):
    """User-defined Click options must still flow through unchanged."""
    _stub_config(monkeypatch)
    _stub_client(monkeypatch)

    @click.command()
    @click.argument("tree_id")
    @click.option("--json-output", "as_json", is_flag=True)
    @qluent_command
    def my_cmd(client, config, tree_id, *, as_json):
        return simple_result({"tree": tree_id}, formatter=lambda d: f"tree={d['tree']}")

    out = CliRunner().invoke(my_cmd, ["growth"]).output.strip()
    assert out == "tree=growth"


def test_qluent_command_returning_none_emits_nothing(monkeypatch):
    """Some commands (e.g. `qluent login`) handle their own output and
    don't return a Result.  The decorator must not crash on `None`."""
    _stub_config(monkeypatch)
    _stub_client(monkeypatch)

    @click.command()
    @click.option("--json-output", "as_json", is_flag=True)
    @qluent_command
    def my_cmd(client, config, *, as_json):
        click.echo("custom output")
        return None

    out = CliRunner().invoke(my_cmd, []).output.strip()
    assert out == "custom output"
