"""Run lifecycle for tree investigations.

A *run* is one execution of an investigation against the Qluent API. Whether
it is launched from `qluent trees investigate`, `qluent trees deep-dive`, or
the `qluent_investigate` / `qluent_deep_dive` MCP tools, the same lifecycle
applies:

    start -> progress -> server-call -> sanitize -> complete

This module owns that lifecycle. `trees.py` (Click command) and `mcp_server.py`
(MCP tool) are thin adapters over the public interface here. There is no
private-import coupling between the two adapters.

Public surface:
    * `RunReporter` - emits start/progress/complete to stderr or JSONL stdout.
    * `collect_tree_metadata` - indexes `list_trees()` output for sanitization.
    * `sanitize_recommended_next_steps` - cleans agent next-step suggestions in
      an investigation bundle.
    * `run_investigation` - orchestrates a single tree investigation: client
      call + sanitization. Used by both adapters.
"""

from __future__ import annotations

import json
import shlex
import threading
import time
import uuid
from typing import Any

import click

from qluent_cli.client import ProgressCallback, QluentClient
from qluent_cli.output import echo_status


class RunReporter:
    """Emit run lifecycle events to stderr (human) or stdout JSONL (stream).

    A reporter is created once per run and tracks elapsed time from
    construction. Concurrent calls (e.g. from the deep-dive thread pool) are
    serialized via an internal lock so JSONL events never interleave.
    """

    def __init__(
        self,
        *,
        command: str,
        stream: bool,
        tree_id: str | None = None,
        tree_count: int | None = None,
        period_label: str,
    ) -> None:
        self.command = command
        self.stream = stream
        self.tree_id = tree_id
        self.tree_count = tree_count
        self.period_label = period_label
        self.run_id = str(uuid.uuid4())
        self.started_at = time.monotonic()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.stream:
            payload: dict[str, Any] = {
                "type": "run.started",
                "run_id": self.run_id,
                "command": self.command,
                "period": self.period_label,
            }
            if self.tree_id is not None:
                payload["tree"] = self.tree_id
            if self.tree_count is not None:
                payload["tree_count"] = self.tree_count
            self._emit_jsonl(payload)
            return

        target = self.tree_id or f"{self.tree_count} tree(s)"
        echo_status(f"[qluent] {self.command} {target} period={self.period_label} starting...")

    def progress(
        self,
        stage: str,
        *,
        tree_id: str | None = None,
        elapsed: float | None = None,
    ) -> None:
        elapsed_ms = int(((elapsed or (time.monotonic() - self.started_at)) * 1000))
        if self.stream:
            payload: dict[str, Any] = {
                "type": "run.progress",
                "run_id": self.run_id,
                "stage": stage,
                "elapsed_ms": elapsed_ms,
            }
            if tree_id is not None:
                payload["tree"] = tree_id
            self._emit_jsonl(payload)
            return

        if stage == "awaiting_api":
            seconds = max(0, round(elapsed_ms / 1000))
            suffix = f" ({seconds}s)" if seconds else ""
            prefix = f"[qluent] {tree_id} " if tree_id else "[qluent] "
            echo_status(f"{prefix}awaiting response...{suffix}")
        elif stage == "formatting":
            prefix = f"[qluent] {tree_id} " if tree_id else "[qluent] "
            echo_status(f"{prefix}received, formatting...")

    def complete(self, result: dict[str, Any], *, run_id: str | None = None) -> None:
        if not self.stream:
            return
        self._emit_jsonl(
            {
                "type": "run.completed",
                "run_id": run_id or self.run_id,
                "elapsed_ms": int((time.monotonic() - self.started_at) * 1000),
                "result": result,
            }
        )

    def _emit_jsonl(self, payload: dict[str, Any]) -> None:
        with self._lock:
            click.echo(json.dumps(payload, separators=(",", ":")))


def collect_tree_metadata(
    trees_data: dict[str, Any],
) -> tuple[set[str], dict[str, set[str]]]:
    """Index `list_trees()` output for next-step sanitization.

    Returns `(available_tree_ids, metrics_by_tree)`:
        * `available_tree_ids` - the set of valid tree ids in the project.
        * `metrics_by_tree`    - tree id -> set of metric/node ids it exposes.
    """
    tree_ids: set[str] = set()
    metrics_by_tree: dict[str, set[str]] = {}
    for tree in trees_data.get("trees") or []:
        tree_id = tree.get("id")
        if not tree_id:
            continue
        tree_id = str(tree_id)
        tree_ids.add(tree_id)
        metrics: set[str] = set()
        for node in tree.get("nodes") or []:
            node_id = node.get("id") or node.get("node_id")
            if node_id:
                metrics.add(str(node_id))
        metrics_by_tree[tree_id] = metrics
    return tree_ids, metrics_by_tree


def _option_start(tokens: list[str]) -> int:
    for index, token in enumerate(tokens):
        if token.startswith("-"):
            return index
    return len(tokens)


def _convert_metric_compare_command(
    *,
    primary_tree: str,
    metric_id: str,
    option_tokens: list[str],
) -> str:
    command = ["qluent", "rca", "analyze", primary_tree, "--metric", metric_id]
    command.extend(option_tokens)
    return " ".join(shlex.quote(token) for token in command)


def sanitize_recommended_next_steps(
    bundle: dict[str, Any],
    *,
    available_tree_ids: set[str],
    metrics_by_tree: dict[str, set[str]],
) -> None:
    """In-place: drop or rewrite agent-recommended `qluent trees compare`
    commands that target non-tree ids.

    Two cases are rewritten in place rather than discarded:
      * `compare <tree> <metric>` where `<metric>` is a node id in `<tree>` -
        rewritten to `rca analyze <tree> --metric <metric>`.

    Anything else with unknown targets has its `command` removed and a
    diagnostic appended to `why`.
    """
    agent = bundle.get("agent")
    if not isinstance(agent, dict):
        return

    next_steps = agent.get("recommended_next_steps")
    if not isinstance(next_steps, list):
        return

    for step in next_steps:
        if not isinstance(step, dict):
            continue
        command = step.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        try:
            tokens = shlex.split(command)
        except ValueError:
            step.pop("command", None)
            step["why"] = (step.get("why") or "Recommended command was malformed.").rstrip()
            continue
        if tokens[:3] != ["qluent", "trees", "compare"]:
            continue

        start = _option_start(tokens[3:])
        tree_args = tokens[3 : 3 + start]
        option_tokens = tokens[3 + start :]
        invalid_targets = [target for target in tree_args if target not in available_tree_ids]
        if not invalid_targets:
            continue

        primary_tree = tree_args[0] if tree_args else str(bundle.get("tree_id") or "")
        if (
            len(tree_args) == 2
            and len(invalid_targets) == 1
            and primary_tree in available_tree_ids
            and invalid_targets[0] in metrics_by_tree.get(primary_tree, set())
        ):
            metric_id = invalid_targets[0]
            step["command"] = _convert_metric_compare_command(
                primary_tree=primary_tree,
                metric_id=metric_id,
                option_tokens=option_tokens,
            )
            step["why"] = (
                (step.get("why") or "").rstrip()
                + f" Converted from compare because `{metric_id}` is a metric in `{primary_tree}`, not a tree id."
            ).strip()
            continue

        step.pop("command", None)
        step["why"] = (
            (step.get("why") or "").rstrip()
            + " No executable command emitted because compare targets must be available tree ids: "
            + ", ".join(sorted(available_tree_ids))
            + "."
        ).strip()


def run_investigation(
    client: QluentClient,
    *,
    tree_id: str,
    current_from: str,
    current_to: str,
    comparison_from: str,
    comparison_to: str,
    trees_data: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    **investigation_kwargs: Any,
) -> dict[str, Any]:
    """Run one tree investigation and return the sanitized bundle.

    The single shared seam between the CLI and MCP adapters. `trees_data`
    is used to validate agent-recommended next steps; if `None`, it is
    fetched via `client.list_trees()`.
    """
    if trees_data is None:
        trees_data = client.list_trees()
    bundle = client.investigate_tree(
        tree_id,
        current_from,
        current_to,
        comparison_from,
        comparison_to,
        progress_callback=progress_callback,
        **investigation_kwargs,
    )
    available_tree_ids, metrics_by_tree = collect_tree_metadata(trees_data)
    sanitize_recommended_next_steps(
        bundle,
        available_tree_ids=available_tree_ids,
        metrics_by_tree=metrics_by_tree,
    )
    return bundle
