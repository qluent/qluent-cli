"""MCP server exposing the Qluent client as Model Context Protocol tools.

The server wraps the same `QluentClient` methods that back the `qluent` CLI, so
non-Claude agents (Codex CLI, Cursor, Continue, Zed, ...) can call qluent
through the standard MCP stdio transport without per-agent forks.

Tool outputs reuse the existing JSON contracts emitted by `--json-output`. No
divergence from the CLI shape.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from qluent_cli import __version__
from qluent_cli.client import QluentClient
from qluent_cli.client_configs import RcaParams
from qluent_cli.config import QluentConfig, load_config
from qluent_cli.elasticity import analyze_elasticity
from qluent_cli.plan_contracts import build_catalog_contract, build_plan_contract
from qluent_cli.query_contracts import build_query_contract
from qluent_cli.runs import run_investigation
from qluent_cli.suggestions import build_suggestions
from qluent_cli.utils import parse_filters
from qluent_cli.window_resolver import resolve_period


SERVER_NAME = "qluent"


def _filters_from_arg(filters_arg: Any) -> dict[str, list[str]]:
    """Normalize the various filter shapes accepted by tools into the dict form.

    Accepted shapes:
      * dict[str, list[str]]      -> returned unchanged (after light coercion)
      * list[str] of "k=v"        -> parsed via parse_filters
      * None / missing            -> {}
    """
    if not filters_arg:
        return {}
    if isinstance(filters_arg, dict):
        normalized: dict[str, list[str]] = {}
        for key, value in filters_arg.items():
            if isinstance(value, list):
                normalized[str(key)] = [str(v) for v in value]
            else:
                normalized[str(key)] = [str(value)]
        return normalized
    if isinstance(filters_arg, list):
        return parse_filters(tuple(str(item) for item in filters_arg))
    raise ValueError("filters must be a dict, list of 'key=value' strings, or null")


def _resolve_dates(
    period: str | None,
    current_range: str | None,
    compare_range: str | None,
) -> tuple[str, str, str, str]:
    return resolve_period(
        period=period,
        current_range=current_range,
        compare_range=compare_range,
    ).windows.iso_tuple()


def _filter_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            {
                "type": "array",
                "items": {"type": "string"},
            },
        ],
        "description": (
            "Filters as either a dimension -> values map or a list of "
            "'dimension=value' strings."
        ),
    }


def _tool_definitions() -> list[dict[str, Any]]:
    """Static tool schemas. Inputs mirror the CLI flags 1:1 where possible."""
    period_props = {
        "period": {
            "type": "string",
            "description": (
                'Natural-language period like "last week", "this month", '
                'or "last 30 days". Mutually exclusive with current/compare.'
            ),
        },
        "current": {
            "type": "string",
            "description": 'Current window as "YYYY-MM-DD:YYYY-MM-DD".',
        },
        "compare": {
            "type": "string",
            "description": 'Comparison window as "YYYY-MM-DD:YYYY-MM-DD".',
        },
    }
    rca_props = {
        "segment_by": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dimensions to consider for segment RCA.",
        },
        "filters": {
            **_filter_schema(),
        },
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 6, "default": 3},
        "max_branches": {"type": "integer", "minimum": 1, "maximum": 10, "default": 2},
        "max_segments": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        "min_contribution_share": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "default": 0.1,
        },
    }

    return [
        {
            "name": "qluent_list_trees",
            "description": "List the metric trees available in the connected project.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "qluent_get_tree",
            "description": "Return the structure (nodes, formulas, metadata) of a single metric tree.",
            "inputSchema": {
                "type": "object",
                "properties": {"tree_id": {"type": "string"}},
                "required": ["tree_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_evaluate",
            "description": (
                "Evaluate a metric tree over a current and comparison window. Returns "
                "node values, deltas, contributions, sensitivities, and elasticities."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string"},
                    **period_props,
                },
                "required": ["tree_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_investigate",
            "description": (
                "Run the deterministic multi-step investigation bundle for a tree: "
                "evaluation + trend + RCA + agent next-step recommendations."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string"},
                    **period_props,
                    "trend_periods": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 52,
                        "default": 4,
                    },
                    "trend_grain": {
                        "type": "string",
                        "enum": ["week", "month"],
                        "default": "week",
                    },
                    "trend_as_of": {"type": "string"},
                    "compare_trees": {"type": "array", "items": {"type": "string"}},
                    **rca_props,
                },
                "required": ["tree_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_deep_dive",
            "description": (
                "Run investigations across multiple trees in parallel and return a bundle "
                "keyed by tree id. If `tree_ids` is omitted, every tree in the project is used."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_ids": {"type": "array", "items": {"type": "string"}},
                    **period_props,
                    "trend_periods": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 52,
                        "default": 4,
                    },
                    "trend_grain": {
                        "type": "string",
                        "enum": ["week", "month"],
                        "default": "week",
                    },
                    "trend_as_of": {"type": "string"},
                    **rca_props,
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_rca_analyze",
            "description": "Run deterministic root-cause analysis for a metric tree (or a single metric within it).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string"},
                    "metric": {
                        "type": "string",
                        "description": "Metric node to start the RCA from. Defaults to the tree root.",
                    },
                    **period_props,
                    **rca_props,
                },
                "required": ["tree_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_elasticity",
            "description": "Analyze observed elasticity between a lever metric and an outcome metric.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_id": {"type": "string"},
                    "outcome": {"type": "string"},
                    "lever": {"type": "string"},
                    "dimension": {"type": "string"},
                    **period_props,
                    "filters": rca_props["filters"],
                },
                "required": ["tree_id", "outcome", "lever"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_query",
            "description": (
                "Ask an ad-hoc natural-language question against the project's data. "
                "Runs the LLM query workflow (NL -> SQL -> execution) — non-deterministic, "
                "may take minutes. Use for row-level or arbitrary questions not covered by "
                "metric trees; prefer the deterministic tree tools when one fits. Pass "
                "thread_id from a previous result to follow up or answer a clarification "
                "(status = clarification_needed)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The natural-language question to answer.",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": (
                            "Thread id from a previous qluent_query result for "
                            "follow-ups or clarification answers."
                        ),
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_compose_catalog",
            "description": (
                "Fetch the project's closed-world query catalog: bases (with "
                "columns), metrics (with the bases that can compute them), "
                "relationships, derived dimensions and aliases — plus the "
                "QueryPlan JSON schema (plan_schema) accepted by "
                "qluent_compose_query. Fetch once per session; it is the whole "
                "vocabulary needed to author plans."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_compose_query",
            "description": (
                "Compile and execute a typed QueryPlan against the project's "
                "query catalog (see qluent_compose_catalog). Deterministic and "
                "correct-by-construction: the same plan always produces the "
                "same SQL, and anything outside the catalog is rejected with "
                "status 'plan_invalid' and a repairable error message — fix "
                "the plan and retry. A status of 'error' is not repairable "
                "(QUERY_CATALOG_INVALID means the project's catalog does not "
                "load, so no plan will compile). Prefer this over qluent_query "
                "when the catalog vocabulary covers the question. When combining "
                "several results, aggregate early (group_by) and only add "
                "metrics whose metadata marks them summable."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "object",
                        "description": (
                            "QueryPlan document; must satisfy the plan_schema "
                            "from qluent_compose_catalog."
                        ),
                    },
                },
                "required": ["plan"],
                "additionalProperties": False,
            },
        },
        {
            "name": "qluent_suggestions",
            "description": (
                "Return project-specific example questions and matching CLI commands "
                "derived deterministically from tree metadata."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tree_id": {
                        "type": "string",
                        "description": "Optional tree id to filter suggestions to a single tree.",
                    }
                },
                "additionalProperties": False,
            },
        },
    ]


ToolHandler = Callable[[QluentClient, QluentConfig, dict[str, Any]], Awaitable[dict[str, Any]]]


async def _list_trees(client: QluentClient, _config: QluentConfig, _args: dict[str, Any]) -> dict[str, Any]:
    return client.list_trees()


async def _get_tree(client: QluentClient, _config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    return client.get_tree(args["tree_id"])


async def _evaluate(client: QluentClient, _config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    c_from, c_to, p_from, p_to = _resolve_dates(
        args.get("period"), args.get("current"), args.get("compare")
    )
    return client.evaluate_tree(args["tree_id"], c_from, c_to, p_from, p_to)


async def _investigate(client: QluentClient, _config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    c_from, c_to, p_from, p_to = _resolve_dates(
        args.get("period"), args.get("current"), args.get("compare")
    )
    return run_investigation(
        client,
        tree_id=args["tree_id"],
        current_from=c_from,
        current_to=c_to,
        comparison_from=p_from,
        comparison_to=p_to,
        trend_periods=int(args.get("trend_periods", 4)),
        trend_grain=str(args.get("trend_grain", "week")),
        trend_as_of=args.get("trend_as_of"),
        segment_by=list(args.get("segment_by") or []),
        filters=_filters_from_arg(args.get("filters")),
        compare_trees=list(args.get("compare_trees") or []),
        max_depth=int(args.get("max_depth", 3)),
        max_branching=int(args.get("max_branches", 2)),
        max_segments=int(args.get("max_segments", 5)),
        min_contribution_share=float(args.get("min_contribution_share", 0.1)),
    )


async def _deep_dive(client: QluentClient, _config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    c_from, c_to, p_from, p_to = _resolve_dates(
        args.get("period"), args.get("current"), args.get("compare")
    )
    trees_data = client.list_trees()
    available = [t.get("id") for t in trees_data.get("trees") or [] if t.get("id")]
    requested = list(args.get("tree_ids") or [])
    if requested:
        unknown = sorted(set(requested) - set(available))
        if unknown:
            raise ValueError(
                f"Unknown tree(s): {', '.join(unknown)}. Available: {', '.join(available)}"
            )
        targets = requested
    else:
        targets = available
    if not targets:
        raise ValueError("No trees available for this project.")

    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for tid in targets:
        try:
            results[tid] = run_investigation(
                client,
                tree_id=tid,
                current_from=c_from,
                current_to=c_to,
                comparison_from=p_from,
                comparison_to=p_to,
                trees_data=trees_data,
                trend_periods=int(args.get("trend_periods", 4)),
                trend_grain=str(args.get("trend_grain", "week")),
                trend_as_of=args.get("trend_as_of"),
                max_depth=int(args.get("max_depth", 3)),
                max_branching=int(args.get("max_branches", 2)),
                max_segments=int(args.get("max_segments", 5)),
                min_contribution_share=float(args.get("min_contribution_share", 0.1)),
            )
        except Exception as exc:
            errors[tid] = f"{type(exc).__name__}: {exc}"

    return {
        "period": {
            "current_from": c_from,
            "current_to": c_to,
            "comparison_from": p_from,
            "comparison_to": p_to,
        },
        "trees_requested": targets,
        "trees": results,
        "errors": errors,
    }


async def _rca_analyze(client: QluentClient, config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    c_from, c_to, p_from, p_to = _resolve_dates(
        args.get("period"), args.get("current"), args.get("compare")
    )
    defaults = RcaParams()
    return client.root_cause_tree(
        args["tree_id"],
        c_from,
        c_to,
        p_from,
        p_to,
        params=RcaParams(
            metric=args.get("metric"),
            segment_by=tuple(args.get("segment_by") or ()),
            filters=_filters_from_arg(args.get("filters")),
            max_depth=int(args.get("max_depth", defaults.max_depth)),
            max_branching=int(args.get("max_branches", defaults.max_branching)),
            max_segments=int(args.get("max_segments", defaults.max_segments)),
            min_contribution_share=float(
                args.get("min_contribution_share", defaults.min_contribution_share)
            ),
        ),
    )


async def _elasticity(client: QluentClient, config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    c_from, c_to, p_from, p_to = _resolve_dates(
        args.get("period"), args.get("current"), args.get("compare")
    )
    return analyze_elasticity(
        client,
        config,
        tree_id=args["tree_id"],
        outcome=args["outcome"],
        lever=args["lever"],
        dimension=args.get("dimension"),
        current_from=c_from,
        current_to=c_to,
        comparison_from=p_from,
        comparison_to=p_to,
        filters=_filters_from_arg(args.get("filters")),
    )


async def _query(client: QluentClient, config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    raw = client.query(args["question"], thread_id=args.get("thread_id"))
    return build_query_contract(raw, config)


async def _suggestions(client: QluentClient, _config: QluentConfig, args: dict[str, Any]) -> dict[str, Any]:
    trees_data = client.list_trees()
    items = build_suggestions(trees_data)
    tree_id = args.get("tree_id")
    if tree_id:
        items = [item for item in items if item.get("tree_id") == tree_id]
    return {"suggestions": items}


async def _compose_catalog(
    client: QluentClient, config: QluentConfig, _args: dict[str, Any]
) -> dict[str, Any]:
    raw = client.get_query_catalog()
    return build_catalog_contract(raw, config)


async def _compose_query(
    client: QluentClient, config: QluentConfig, args: dict[str, Any]
) -> dict[str, Any]:
    plan = args.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("'plan' must be a QueryPlan JSON object")
    raw = client.execute_plan(plan)
    return build_plan_contract(raw, config)


HANDLERS: dict[str, ToolHandler] = {
    "qluent_list_trees": _list_trees,
    "qluent_get_tree": _get_tree,
    "qluent_evaluate": _evaluate,
    "qluent_investigate": _investigate,
    "qluent_deep_dive": _deep_dive,
    "qluent_rca_analyze": _rca_analyze,
    "qluent_elasticity": _elasticity,
    "qluent_query": _query,
    "qluent_compose_catalog": _compose_catalog,
    "qluent_compose_query": _compose_query,
    "qluent_suggestions": _suggestions,
}


async def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    client: QluentClient,
    config: QluentConfig,
) -> dict[str, Any]:
    """Route an MCP tool call to the right handler. Used by tests and the server."""
    handler = HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    return await handler(client, config, arguments or {})


def build_server() -> Any:
    """Construct the low-level MCP `Server` with all qluent tools registered."""
    from mcp.server.lowlevel import Server
    from mcp import types

    server: Any = Server(SERVER_NAME, version=__version__)
    tool_defs = _tool_definitions()
    tools = [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in tool_defs
    ]

    @server.list_tools()
    async def _list() -> list[Any]:
        return tools

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[Any]:
        try:
            config = load_config()
            client = QluentClient(config)
            payload = await dispatch_tool(name, arguments or {}, client=client, config=config)
        except SystemExit as exc:
            message = str(exc) or f"exit {exc.code}"
            return [types.TextContent(type="text", text=f"Error: {message}")]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]
        return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]

    return server


async def serve_stdio() -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects."""
    from mcp.server.stdio import stdio_server
    from mcp.server import NotificationOptions
    from mcp.server.models import InitializationOptions

    server = build_server()
    init_options = InitializationOptions(
        server_name=SERVER_NAME,
        server_version=__version__,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)
