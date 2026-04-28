"""Metric tree commands — list, evaluate, trend, compare, investigate."""

from __future__ import annotations

import json
import shlex
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as dt_date
from typing import Any

import click

from qluent_cli import sessions
from qluent_cli.client import QluentClient
from qluent_cli.config import QluentConfig, load_config
from qluent_cli.output import echo_status
from qluent_cli.tree_contracts import build_tree_query_contract
from qluent_cli.formatters import (
    format_comparison,
    format_evaluation,
    format_investigation,
    format_levers,
    format_period_label,
    format_trend,
    format_tree_detail,
    format_tree_list,
    format_tree_validation,
)
from qluent_cli.utils import parse_filters, resolve_date_args


@click.group()
def trees() -> None:
    """Metric tree commands."""


def _profile_for(config: QluentConfig) -> str:
    return f"{config.user_email}@{config.api_url}"


def _resume_or_last(
    *,
    command: str,
    resume: str | None,
    use_last: bool,
    tree_id: str | None,
) -> sessions.RunRecord | None:
    """Resolve --resume / --last to a stored run; raises if requested but missing."""
    if resume and use_last:
        raise click.ClickException("Use either --resume or --last, not both.")
    if resume:
        record = sessions.get_run(resume)
        if record is None:
            raise click.ClickException(f"No run found for run_id={resume}")
        if record.command != command:
            raise click.ClickException(
                f"Run {resume} is a {record.command!r} run, not {command!r}."
            )
        if tree_id and record.tree_id and record.tree_id != tree_id:
            raise click.ClickException(
                f"Run {resume} is for tree {record.tree_id!r}, not {tree_id!r}."
            )
        return record
    if use_last:
        record = sessions.find_last_run(command=command, tree_id=tree_id)
        if record is None:
            target = f" for {tree_id}" if tree_id else ""
            raise click.ClickException(
                f"No prior {command!r} run{target} found. Run it once to populate the cache."
            )
        return record
    return None


def _persist_run_safely(**kwargs):
    try:
        return sessions.record_run(**kwargs)
    except Exception as exc:
        click.echo(f"Warning: failed to persist run: {exc}", err=True)
        return None


_DEFAULT_LEVER_SCENARIOS = (0.01, 0.05, 0.10)
_LEVER_KEYWORDS = (
    "elasticity",
    "sensitivity",
    "lever",
    "levers",
    "impact",
    "what if",
    "what-if",
    "scenario",
    "scenarios",
    "if we",
    "increase",
    "decrease",
)


class _RunReporter:
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

    def progress(self, stage: str, *, tree_id: str | None = None, elapsed: float | None = None) -> None:
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


def _is_lever_question(question: str | None) -> bool:
    if not question:
        return False
    question_lower = question.lower()
    return any(keyword in question_lower for keyword in _LEVER_KEYWORDS)


def _build_lever_analysis(
    evaluation: dict[str, Any],
    *,
    top_n: int,
    scenarios: tuple[float, ...] | list[float],
) -> dict[str, Any] | None:
    """Build a deterministic lever summary from evaluation elasticities."""
    if not evaluation:
        return None

    current_root_value = evaluation.get("current_value")
    if not isinstance(current_root_value, (int, float)):
        return None

    deduped_scenarios: list[float] = []
    seen_scenarios: set[float] = set()
    for scenario in scenarios:
        scenario_value = float(scenario)
        if scenario_value <= 0 or scenario_value in seen_scenarios:
            continue
        seen_scenarios.add(scenario_value)
        deduped_scenarios.append(scenario_value)
    if not deduped_scenarios:
        deduped_scenarios = list(_DEFAULT_LEVER_SCENARIOS)

    root_node_id = evaluation.get("root_node_id")
    ranked_levers: list[tuple[float, dict[str, Any]]] = []
    for node in evaluation.get("nodes") or []:
        node_id = node.get("id")
        elasticity = node.get("elasticity")
        if node_id == root_node_id or elasticity is None:
            continue
        if not isinstance(elasticity, (int, float)):
            continue

        recommended_direction = "neutral"
        if elasticity > 0:
            recommended_direction = "increase"
        elif elasticity < 0:
            recommended_direction = "decrease"

        scenario_impacts = [
            {
                "node_change_ratio": scenario,
                "estimated_root_delta_ratio": elasticity * scenario,
                "estimated_root_delta_value": current_root_value * elasticity * scenario,
            }
            for scenario in deduped_scenarios
        ]

        ranked_levers.append(
            (
                abs(elasticity),
                {
                    "node_id": node_id,
                    "label": node.get("label") or node_id,
                    "current_value": node.get("current_value"),
                    "delta_value": node.get("delta_value"),
                    "delta_ratio": node.get("delta_ratio"),
                    "sensitivity": node.get("sensitivity"),
                    "elasticity": elasticity,
                    "recommended_direction": recommended_direction,
                    "scenario_impacts": scenario_impacts,
                },
            )
        )

    ranked_levers.sort(key=lambda item: item[0], reverse=True)
    top_levers = [item[1] for item in ranked_levers[:top_n]]

    warnings: list[str] = []
    if not top_levers:
        warnings.append("No non-root nodes had defined elasticities for this tree.")
    warnings.append(
        "Lever impacts are local linear estimates based on current elasticities; treat them as directional guidance, not forecasts."
    )

    return {
        "tree_id": evaluation.get("tree_id"),
        "tree_label": evaluation.get("tree_label"),
        "root_node_id": root_node_id,
        "current_window": evaluation.get("current_window"),
        "comparison_window": evaluation.get("comparison_window"),
        "current_value": current_root_value,
        "comparison_value": evaluation.get("comparison_value"),
        "delta_value": evaluation.get("delta_value"),
        "delta_ratio": evaluation.get("delta_ratio"),
        "scenarios": deduped_scenarios,
        "top_levers": top_levers,
        "warnings": warnings,
    }


def _collect_lever_findings(bundle: dict[str, Any]) -> list[str]:
    """Summarize the strongest available lever signals."""
    levers = bundle.get("levers") or {}
    top_levers = levers.get("top_levers") or []
    if not top_levers:
        return []

    scenario_lookup = {}
    for impact in top_levers[0].get("scenario_impacts") or []:
        scenario_lookup[impact.get("node_change_ratio")] = impact
    preferred_scenario = scenario_lookup.get(0.05)
    if preferred_scenario is None:
        preferred_scenario = (top_levers[0].get("scenario_impacts") or [None])[0]
    if preferred_scenario is None:
        return []

    label = top_levers[0].get("label") or top_levers[0].get("node_id") or "Unknown"
    elasticity = top_levers[0].get("elasticity")
    change_ratio = preferred_scenario.get("node_change_ratio", 0)
    root_ratio = preferred_scenario.get("estimated_root_delta_ratio", 0)
    root_value = preferred_scenario.get("estimated_root_delta_value", 0)
    return [
        f"{label} is the biggest lever (ε {elasticity:+.2f}); +{change_ratio * 100:.0f}% implies root {root_ratio * 100:+.1f}% (Δ {root_value:+.0f})."
    ]


def _collect_trend_evaluations(
    client: QluentClient,
    tree_id: str,
    periods: int,
    grain: str,
    as_of: str | None,
) -> list[dict[str, Any]]:
    from qluent_cli.dates import generate_consecutive_windows

    ref_date = dt_date.fromisoformat(as_of) if as_of else None
    window_pairs = generate_consecutive_windows(periods, grain, today=ref_date)
    evaluations: list[dict[str, Any]] = []
    for window_pair in window_pairs:
        data = client.evaluate_tree(
            tree_id,
            str(window_pair.current.date_from),
            str(window_pair.current.date_to),
            str(window_pair.comparison.date_from),
            str(window_pair.comparison.date_to),
        )
        evaluations.append(data)
    return evaluations


def _collect_tree_metadata(trees_data: dict[str, Any]) -> tuple[set[str], dict[str, set[str]]]:
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


def _sanitize_recommended_next_steps(
    bundle: dict[str, Any],
    *,
    available_tree_ids: set[str],
    metrics_by_tree: dict[str, set[str]],
) -> None:
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



@trees.command(name="list")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def list_trees(as_json: bool) -> None:
    """List available metric trees."""
    client = QluentClient(load_config())
    data = client.list_trees()

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_list(data))


@trees.command()
@click.argument("tree_id")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def get(tree_id: str, as_json: bool) -> None:
    """Show the structure of a metric tree."""
    client = QluentClient(load_config())
    data = client.get_tree(tree_id)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_detail(data))


@trees.command()
@click.argument("tree_id")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def validate(tree_id: str, as_json: bool) -> None:
    """Validate a saved metric tree against its referenced metric SQL."""
    client = QluentClient(load_config())
    data = client.validate_tree(tree_id)

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_tree_validation(data))


@trees.command()
@click.argument("tree_id")
@click.option("--period", "-p", default=None, help='Period like "last week", "this month", "last 30 days"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--contract-output", is_flag=True, help="Output the deterministic tree query contract")
def evaluate(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    as_json: bool,
    contract_output: bool,
) -> None:
    """Evaluate a metric tree over date windows."""
    if as_json and contract_output:
        raise click.ClickException("Use either --json-output or --contract-output, not both.")
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    config = load_config()
    client = QluentClient(config)
    data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)

    if contract_output:
        click.echo(json.dumps(build_tree_query_contract(data, config), indent=2))
    elif as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_evaluation(data))


@trees.command()
@click.argument("tree_id")
@click.option("--period", "-p", default=None, help='Period like "last week", "this month", "last 30 days"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--top", default=5, type=click.IntRange(1, 20), help="Number of top levers to show")
@click.option(
    "--scenario",
    "scenarios",
    multiple=True,
    type=click.FloatRange(0.0, 1.0),
    default=_DEFAULT_LEVER_SCENARIOS,
    help="Node change ratio to evaluate, expressed as a decimal (repeatable, e.g. 0.05 for +5%)",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def levers(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    top: int,
    scenarios: tuple[float, ...],
    as_json: bool,
) -> None:
    """Quantify top lever impacts from tree elasticities."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    client = QluentClient(load_config())
    evaluation = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)
    data = _build_lever_analysis(evaluation, top_n=top, scenarios=scenarios)
    if data is None:
        raise click.ClickException("Could not compute lever analysis from the evaluation result.")

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(format_levers(data))


@trees.command()
@click.argument("tree_id")
@click.option("--periods", "-n", default=4, type=click.IntRange(1, 52), help="Number of consecutive periods (default: 4)")
@click.option("--grain", "-g", default="week", type=click.Choice(["week", "month"]), help="Period granularity")
@click.option("--as-of", "as_of", default=None, help="Reference date as YYYY-MM-DD (default: today)")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def trend(tree_id: str, periods: int, grain: str, as_of: str | None, as_json: bool) -> None:
    """Show multi-period trend for a metric tree."""
    client = QluentClient(load_config())
    evaluations = _collect_trend_evaluations(client, tree_id, periods, grain, as_of)

    if as_json:
        click.echo(json.dumps(evaluations, indent=2))
    else:
        tree_label = evaluations[0].get("tree_label", tree_id) if evaluations else tree_id
        click.echo(format_trend(tree_label, evaluations, grain))


@trees.command()
@click.argument("tree_ids", nargs=-1, required=True)
@click.option("--period", "-p", default=None, help='Period like "last week", "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
def compare(
    tree_ids: tuple[str, ...],
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    as_json: bool,
) -> None:
    """Compare multiple metric trees side by side for the same period."""
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)

    client = QluentClient(load_config())
    results: list[tuple[str, dict[str, Any]]] = []
    for tree_id in tree_ids:
        data = client.evaluate_tree(tree_id, c_from, c_to, p_from, p_to)
        results.append((data.get("tree_label", tree_id), data))

    if as_json:
        click.echo(json.dumps([data for _, data in results], indent=2))
    else:
        click.echo(format_comparison(results, format_period_label(c_from, c_to, p_from, p_to)))


@trees.command()
@click.argument("tree_id")
@click.option("--period", "-p", default=None, help='Period like "last week" or "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--trend-periods", default=4, type=click.IntRange(1, 52), help="Number of periods for the bundled trend step")
@click.option("--trend-grain", default="week", type=click.Choice(["week", "month"]), help="Granularity for the bundled trend step")
@click.option("--trend-as-of", default=None, help="Reference date for bundled trend as YYYY-MM-DD")
@click.option("--segment-by", "segment_by", multiple=True, help="Dimension to consider for segment RCA (repeatable)")
@click.option("--filter", "filters", multiple=True, help="Filter as dimension=value (repeatable)")
@click.option("--compare-tree", "compare_trees", multiple=True, help="Additional tree to compare against the primary tree")
@click.option("--max-depth", default=3, type=click.IntRange(1, 6), help="Maximum tree depth to traverse in RCA")
@click.option("--max-branches", default=2, type=click.IntRange(1, 10), help="Maximum child branches to follow per node in RCA")
@click.option("--max-segments", default=5, type=click.IntRange(1, 20), help="Maximum segments to show per node in RCA")
@click.option(
    "--min-contribution-share",
    default=0.1,
    type=click.FloatRange(0.0, 1.0),
    help="Minimum absolute direct contribution share required to follow a child branch in RCA",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--stream", is_flag=True, help="Emit JSONL progress events and the final result.")
@click.option("--resume", "resume", default=None, help="Re-print a previously persisted run by run_id (no API call).")
@click.option("--last", "use_last", is_flag=True, help="Re-print the most recent investigate of this tree (no API call).")
def investigate(
    tree_id: str,
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    trend_periods: int,
    trend_grain: str,
    trend_as_of: str | None,
    segment_by: tuple[str, ...],
    filters: tuple[str, ...],
    compare_trees: tuple[str, ...],
    max_depth: int,
    max_branches: int,
    max_segments: int,
    min_contribution_share: float,
    as_json: bool,
    stream: bool,
    resume: str | None,
    use_last: bool,
) -> None:
    """Run a deterministic multi-step investigation bundle for a tree."""
    cached = _resume_or_last(
        command=sessions.INVESTIGATE_COMMAND,
        resume=resume,
        use_last=use_last,
        tree_id=tree_id,
    )
    if cached is not None:
        bundle = cached.load().get("result") or {}
        _emit_investigation(bundle, as_json=as_json, run_id=cached.run_id, from_cache=True)
        return

    config = load_config()
    client = QluentClient(config)
    parsed_filters = parse_filters(filters)
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)
    period_label = format_period_label(c_from, c_to, p_from, p_to)
    reporter = _RunReporter(
        command="investigate",
        stream=stream,
        tree_id=tree_id,
        period_label=period_label,
    )
    if stream or not as_json:
        reporter.start()
    available_tree_ids, metrics_by_tree = _collect_tree_metadata(client.list_trees())
    if stream or not as_json:
        reporter.progress("awaiting_api")

    bundle = client.investigate_tree(
        tree_id,
        c_from,
        c_to,
        p_from,
        p_to,
        trend_periods=trend_periods,
        trend_grain=trend_grain,
        trend_as_of=trend_as_of,
        segment_by=list(segment_by),
        filters=parsed_filters,
        compare_trees=list(compare_trees),
        max_depth=max_depth,
        max_branching=max_branches,
        max_segments=max_segments,
        min_contribution_share=min_contribution_share,
        progress_callback=lambda stage, elapsed: reporter.progress(stage, elapsed=elapsed),
    )
    if stream or not as_json:
        reporter.progress("formatting")
    _sanitize_recommended_next_steps(
        bundle,
        available_tree_ids=available_tree_ids,
        metrics_by_tree=metrics_by_tree,
    )

    record = _persist_run_safely(
        command=sessions.INVESTIGATE_COMMAND,
        tree_id=tree_id,
        period_start=c_from,
        period_end=c_to,
        comparison_start=p_from,
        comparison_end=p_to,
        profile=_profile_for(config),
        client_safe=config.client_safe,
        args={
            "period": period,
            "current": current_range,
            "compare": compare_range,
            "trend_periods": trend_periods,
            "trend_grain": trend_grain,
            "trend_as_of": trend_as_of,
            "segment_by": list(segment_by),
            "filters": parsed_filters,
            "compare_trees": list(compare_trees),
            "max_depth": max_depth,
            "max_branches": max_branches,
            "max_segments": max_segments,
            "min_contribution_share": min_contribution_share,
        },
        payload=bundle,
    )

    if stream:
        reporter.complete(bundle, run_id=record.run_id if record else None)
        return
    _emit_investigation(
        bundle,
        as_json=as_json,
        run_id=record.run_id if record else None,
    )


def _emit_investigation(
    bundle: dict[str, Any],
    *,
    as_json: bool,
    run_id: str | None,
    from_cache: bool = False,
) -> None:
    if as_json:
        click.echo(json.dumps(bundle, indent=2))
    else:
        click.echo(format_investigation(bundle))
        if run_id:
            tag = "(cached)" if from_cache else "(saved)"
            click.echo(f"\nrun_id: {run_id} {tag}")


@trees.command(name="deep-dive")
@click.option("--period", "-p", default=None, help='Period like "last week" or "this month"')
@click.option("--current", "current_range", default=None, help="Current window as YYYY-MM-DD:YYYY-MM-DD")
@click.option("--compare", "compare_range", default=None, help="Comparison window as YYYY-MM-DD:YYYY-MM-DD")
@click.option(
    "--tree",
    "tree_ids",
    multiple=True,
    help="Limit to specific trees (repeatable). Defaults to every tree in the project.",
)
@click.option("--trend-periods", default=4, type=click.IntRange(1, 52))
@click.option("--trend-grain", default="week", type=click.Choice(["week", "month"]))
@click.option("--trend-as-of", default=None, help="Reference date for bundled trend as YYYY-MM-DD")
@click.option("--max-depth", default=3, type=click.IntRange(1, 6))
@click.option("--max-branches", default=2, type=click.IntRange(1, 10))
@click.option("--max-segments", default=5, type=click.IntRange(1, 20))
@click.option(
    "--min-contribution-share",
    default=0.1,
    type=click.FloatRange(0.0, 1.0),
)
@click.option(
    "--max-workers",
    default=4,
    type=click.IntRange(1, 8),
    help="Maximum number of trees to investigate in parallel.",
)
@click.option("--json-output", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--stream", is_flag=True, help="Emit JSONL progress events and the final result.")
@click.option("--resume", "resume", default=None, help="Re-print a previously persisted run by run_id (no API call).")
@click.option("--last", "use_last", is_flag=True, help="Re-print the most recent deep-dive (no API call).")
def deep_dive(
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
    tree_ids: tuple[str, ...],
    trend_periods: int,
    trend_grain: str,
    trend_as_of: str | None,
    max_depth: int,
    max_branches: int,
    max_segments: int,
    min_contribution_share: float,
    max_workers: int,
    as_json: bool,
    stream: bool,
    resume: str | None,
    use_last: bool,
) -> None:
    """Run investigations across every tree in parallel and bundle the results."""
    cached = _resume_or_last(
        command=sessions.DEEP_DIVE_COMMAND,
        resume=resume,
        use_last=use_last,
        tree_id=None,
    )
    if cached is not None:
        bundle = cached.load().get("result") or {}
        _emit_deep_dive(bundle, as_json=as_json, run_id=cached.run_id, from_cache=True)
        return

    config = load_config()
    client = QluentClient(config)
    c_from, c_to, p_from, p_to = resolve_date_args(period, current_range, compare_range)

    trees_data = client.list_trees()
    available = [t.get("id") for t in trees_data.get("trees", []) if t.get("id")]

    if tree_ids:
        unknown = sorted(set(tree_ids) - set(available))
        if unknown:
            raise click.ClickException(
                f"Unknown tree(s): {', '.join(unknown)}. Available: {', '.join(available)}"
            )
        targets = list(tree_ids)
    else:
        targets = available

    if not targets:
        raise click.ClickException("No trees available for this project.")

    available_tree_ids, metrics_by_tree = _collect_tree_metadata(trees_data)
    period_label = format_period_label(c_from, c_to, p_from, p_to)
    reporter = _RunReporter(
        command="deep-dive",
        stream=stream,
        tree_count=len(targets),
        period_label=period_label,
    )
    if stream or not as_json:
        reporter.start()

    def _investigate(tid: str) -> dict[str, Any]:
        if stream or not as_json:
            reporter.progress("awaiting_api", tree_id=tid)
        bundle = client.investigate_tree(
            tid,
            c_from,
            c_to,
            p_from,
            p_to,
            trend_periods=trend_periods,
            trend_grain=trend_grain,
            trend_as_of=trend_as_of,
            max_depth=max_depth,
            max_branching=max_branches,
            max_segments=max_segments,
            min_contribution_share=min_contribution_share,
            progress_callback=lambda stage, elapsed: reporter.progress(
                stage, tree_id=tid, elapsed=elapsed
            ),
        )
        if stream or not as_json:
            reporter.progress("formatting", tree_id=tid)
        _sanitize_recommended_next_steps(
            bundle,
            available_tree_ids=available_tree_ids,
            metrics_by_tree=metrics_by_tree,
        )
        return bundle

    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    workers = min(max_workers, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_investigate, tid): tid for tid in targets}
        for future in as_completed(futures):
            tid = futures[future]
            try:
                results[tid] = future.result()
            except Exception as exc:
                errors[tid] = f"{type(exc).__name__}: {exc}"

    ordered_results = {tid: results[tid] for tid in targets if tid in results}

    bundle = {
        "period": {
            "current_from": c_from,
            "current_to": c_to,
            "comparison_from": p_from,
            "comparison_to": p_to,
        },
        "trees_requested": targets,
        "trees": ordered_results,
        "errors": errors,
    }

    record: sessions.RunRecord | None = None
    if ordered_results:
        record = _persist_run_safely(
            command=sessions.DEEP_DIVE_COMMAND,
            tree_id=None,
            period_start=c_from,
            period_end=c_to,
            comparison_start=p_from,
            comparison_end=p_to,
            profile=_profile_for(config),
            client_safe=config.client_safe,
            args={
                "period": period,
                "current": current_range,
                "compare": compare_range,
                "tree_ids": list(tree_ids),
                "trend_periods": trend_periods,
                "trend_grain": trend_grain,
                "trend_as_of": trend_as_of,
                "max_depth": max_depth,
                "max_branches": max_branches,
                "max_segments": max_segments,
                "min_contribution_share": min_contribution_share,
                "max_workers": max_workers,
            },
            payload=bundle,
        )

    if stream:
        reporter.complete(bundle, run_id=record.run_id if record else None)
        return

    _emit_deep_dive(
        bundle,
        as_json=as_json,
        run_id=record.run_id if record else None,
    )


def _emit_deep_dive(
    bundle: dict[str, Any],
    *,
    as_json: bool,
    run_id: str | None,
    from_cache: bool = False,
) -> None:
    if as_json:
        click.echo(json.dumps(bundle, indent=2))
        return

    period = bundle.get("period") or {}
    targets = bundle.get("trees_requested") or list((bundle.get("trees") or {}).keys())
    ordered_results = bundle.get("trees") or {}
    errors = bundle.get("errors") or {}
    period_label = format_period_label(
        period.get("current_from") or "",
        period.get("current_to") or "",
        period.get("comparison_from") or "",
        period.get("comparison_to") or "",
    )
    click.echo(f"Deep-dive across {len(targets)} tree(s) — {period_label}")
    click.echo("")
    for tid in targets:
        click.echo("=" * 72)
        click.echo(f"Tree: {tid}")
        click.echo("=" * 72)
        if tid in ordered_results:
            click.echo(format_investigation(ordered_results[tid]))
        else:
            click.echo(f"  Failed: {errors.get(tid, 'unknown error')}")
        click.echo("")
    if run_id:
        tag = "(cached)" if from_cache else "(saved)"
        click.echo(f"run_id: {run_id} {tag}")
