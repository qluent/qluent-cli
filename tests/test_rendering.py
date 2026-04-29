"""Tests for the rendering seam.

The rendering seam is a single place where every command decides between
JSON output (`--json-output`) and human-formatted output. Today every command
duplicates this branch (see issue #76).
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import click

from qluent_cli.rendering import Result, render


def test_render_emits_json_when_as_json_true():
    runner = CliRunner()

    @click.command()
    def cmd() -> None:
        render(Result(json_payload={"hello": "world"}, human="HELLO"), as_json=True)

    out = runner.invoke(cmd).output
    assert json.loads(out) == {"hello": "world"}


def test_render_emits_human_when_as_json_false():
    runner = CliRunner()

    @click.command()
    def cmd() -> None:
        render(Result(json_payload={"hello": "world"}, human="HELLO HUMAN"), as_json=False)

    assert runner.invoke(cmd).output.strip() == "HELLO HUMAN"


def test_render_supports_distinct_json_and_human_payloads():
    """`compare` builds JSON from one shape and human from another."""
    runner = CliRunner()
    json_payload = [{"tree": "a"}, {"tree": "b"}]
    human_text = "compare table"

    @click.command()
    def cmd_json() -> None:
        render(Result(json_payload=json_payload, human=human_text), as_json=True)

    @click.command()
    def cmd_human() -> None:
        render(Result(json_payload=json_payload, human=human_text), as_json=False)

    assert json.loads(runner.invoke(cmd_json).output) == json_payload
    assert runner.invoke(cmd_human).output.strip() == "compare table"


def test_render_lazy_human_is_only_called_when_needed():
    """Avoid running the human formatter when JSON output is requested."""
    runner = CliRunner()
    calls: list[int] = []

    def expensive_formatter() -> str:
        calls.append(1)
        return "expensive"

    @click.command()
    def cmd() -> None:
        render(Result(json_payload={"k": 1}, human=expensive_formatter), as_json=True)

    runner.invoke(cmd)
    assert calls == []  # not invoked on JSON path


def test_render_lazy_human_is_called_when_human_requested():
    runner = CliRunner()
    calls: list[int] = []

    def formatter() -> str:
        calls.append(1)
        return "human"

    @click.command()
    def cmd() -> None:
        render(Result(json_payload={"k": 1}, human=formatter), as_json=False)

    out = runner.invoke(cmd).output.strip()
    assert out == "human"
    assert calls == [1]


def test_render_json_uses_two_space_indent():
    """The legacy call sites all used `json.dumps(..., indent=2)` so output
    diffs in scripts pinned to that shape stay quiet."""
    runner = CliRunner()

    @click.command()
    def cmd() -> None:
        render(Result(json_payload={"a": {"b": 1}}, human="x"), as_json=True)

    out = runner.invoke(cmd).output
    assert out == json.dumps({"a": {"b": 1}}, indent=2) + "\n"


def test_render_handles_list_json_payload():
    runner = CliRunner()

    @click.command()
    def cmd() -> None:
        render(Result(json_payload=[1, 2, 3], human="list"), as_json=True)

    assert json.loads(runner.invoke(cmd).output) == [1, 2, 3]


def test_result_factory_for_simple_case():
    """Common case: same data, single formatter.  Avoid making callers
    construct `Result` by hand for the trivial mapping."""
    from qluent_cli.rendering import simple_result

    data = {"x": 1}
    result = simple_result(data, formatter=lambda d: f"X is {d['x']}")
    assert result.json_payload == data
    # Human payload may be a callable; render() must accept it.
    runner = CliRunner()

    @click.command()
    def cmd() -> None:
        render(result, as_json=False)

    assert runner.invoke(cmd).output.strip() == "X is 1"


def test_render_reads_as_json_from_click_context_if_not_passed():
    """Sugar: when commands don't explicitly pass `as_json`, the renderer
    reads it from the Click context (set by the top-level `--json-output`)."""
    runner = CliRunner()

    @click.command()
    @click.option("--json-output", "as_json", is_flag=True)
    @click.pass_context
    def cmd(ctx: click.Context, as_json: bool) -> None:
        ctx.ensure_object(dict)
        ctx.obj["as_json"] = as_json
        render(Result(json_payload={"k": 1}, human="human"))  # no as_json kwarg

    out = runner.invoke(cmd, ["--json-output"]).output
    assert json.loads(out) == {"k": 1}
    out2 = runner.invoke(cmd, []).output
    assert out2.strip() == "human"
