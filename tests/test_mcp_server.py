from __future__ import annotations

import asyncio
import json
from typing import Any

from click.testing import CliRunner

from qluent_cli.config import QluentConfig
from qluent_cli.main import cli
from qluent_cli.mcp_server import (
    HANDLERS,
    _filters_from_arg,
    _tool_definitions,
    build_server,
    dispatch_tool,
)


CONFIG = QluentConfig(
    api_key="qk_test",
    api_url="https://api.example.com",
    project_uuid="project-123",
    user_email="user@example.com",
)


TREE_DATA: dict[str, Any] = {
    "trees": [
        {
            "id": "revenue",
            "label": "Revenue",
            "root_node_id": "net_revenue",
            "dimensions": ["region"],
            "nodes": [
                {"id": "net_revenue", "label": "Net Revenue", "kind": "formula"},
                {"id": "orders", "label": "Orders", "kind": "sql_metric"},
            ],
        }
    ]
}


class FakeClient:
    """Stand-in for QluentClient that records calls and returns canned payloads."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def list_trees(self) -> dict[str, Any]:
        self.calls.append(("list_trees", (), {}))
        return TREE_DATA

    def get_tree(self, tree_id: str) -> dict[str, Any]:
        self.calls.append(("get_tree", (tree_id,), {}))
        return {"id": tree_id, "nodes": []}

    def evaluate_tree(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, *, windows=None):
        if windows is not None:
            c_from, c_to, p_from, p_to = windows.iso_tuple()
        self.calls.append(
            ("evaluate_tree", (tree_id, c_from, c_to, p_from, p_to), {})
        )
        return {"tree_id": tree_id, "current_value": 100.0, "comparison_value": 90.0}

    def investigate_tree(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        self.calls.append(
            ("investigate_tree", (tree_id, c_from, c_to, p_from, p_to), kwargs)
        )
        return {
            "tree_id": tree_id,
            "agent": {
                "recommended_next_steps": [
                    {
                        "command": "qluent trees compare revenue orders --period 'last 7 days'",
                        "why": "Compare a metric.",
                    }
                ]
            },
        }

    def root_cause_tree(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        # Mirrors the production client: enrichment is part of the
        # `root_cause_tree` contract, not a post-processing step.
        from qluent_cli.rca_contracts import enrich_rca_output

        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        self.calls.append(
            ("root_cause_tree", (tree_id, c_from, c_to, p_from, p_to), kwargs)
        )
        raw = {
            "tree_id": tree_id,
            "root_node_id": tree_id,
            "current_window": {"date_from": c_from, "date_to": c_to},
            "comparison_window": {"date_from": p_from, "date_to": p_to},
            "current_value": 100,
            "comparison_value": 90,
            "delta_value": 10,
            "delta_ratio": 0.111,
            "findings": [],
            "warnings": [],
        }
        return enrich_rca_output(raw, CONFIG)

    def elasticity_tree(self, tree_id, c_from=None, c_to=None, p_from=None, p_to=None, **kwargs):
        if kwargs.get("windows") is not None:
            c_from, c_to, p_from, p_to = kwargs["windows"].iso_tuple()
        self.calls.append(
            ("elasticity_tree", (tree_id, c_from, c_to, p_from, p_to), kwargs)
        )
        return {"tree_id": tree_id}


def test_tool_definitions_cover_acceptance_criteria_tools():
    names = {tool["name"] for tool in _tool_definitions()}
    assert names == {
        "qluent_list_trees",
        "qluent_get_tree",
        "qluent_evaluate",
        "qluent_investigate",
        "qluent_deep_dive",
        "qluent_rca_analyze",
        "qluent_elasticity",
        "qluent_suggestions",
    }
    assert names == set(HANDLERS)


def test_filters_from_arg_accepts_dict_list_and_none():
    assert _filters_from_arg(None) == {}
    assert _filters_from_arg({"region": ["EU", "US"]}) == {"region": ["EU", "US"]}
    assert _filters_from_arg({"region": "EU"}) == {"region": ["EU"]}
    assert _filters_from_arg(["region=EU", "region=US"]) == {"region": ["EU", "US"]}


def test_filter_schema_advertises_dict_and_list_forms():
    analyze = next(tool for tool in _tool_definitions() if tool["name"] == "qluent_rca_analyze")
    filters = analyze["inputSchema"]["properties"]["filters"]
    assert filters["anyOf"] == [
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
    ]


def test_dispatch_list_trees_returns_canned_payload():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool("qluent_list_trees", {}, client=client, config=CONFIG)
    )
    assert result == TREE_DATA
    assert client.calls == [("list_trees", (), {})]


def test_dispatch_evaluate_resolves_period_to_window():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_evaluate",
            {"tree_id": "revenue", "period": "last 7 days"},
            client=client,
            config=CONFIG,
        )
    )
    assert result["tree_id"] == "revenue"
    assert client.calls[0][0] == "evaluate_tree"
    args = client.calls[0][1]
    assert args[0] == "revenue"
    # All four window dates should be ISO YYYY-MM-DD strings.
    for date_str in args[1:]:
        assert len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-"


def test_dispatch_evaluate_accepts_explicit_windows():
    client = FakeClient()
    asyncio.run(
        dispatch_tool(
            "qluent_evaluate",
            {
                "tree_id": "revenue",
                "current": "2026-04-01:2026-04-07",
                "compare": "2026-03-25:2026-03-31",
            },
            client=client,
            config=CONFIG,
        )
    )
    assert client.calls[0][1] == (
        "revenue",
        "2026-04-01",
        "2026-04-07",
        "2026-03-25",
        "2026-03-31",
    )


def test_dispatch_investigate_forwards_rca_options():
    client = FakeClient()
    asyncio.run(
        dispatch_tool(
            "qluent_investigate",
            {
                "tree_id": "revenue",
                "period": "last 7 days",
                "segment_by": ["region"],
                "filters": {"region": ["EU"]},
                "max_depth": 2,
                "max_branches": 3,
            },
            client=client,
            config=CONFIG,
        )
    )
    investigate_call = next(c for c in client.calls if c[0] == "investigate_tree")
    kwargs = investigate_call[2]
    assert kwargs["segment_by"] == ["region"]
    assert kwargs["filters"] == {"region": ["EU"]}
    assert kwargs["max_depth"] == 2
    assert kwargs["max_branching"] == 3


def test_dispatch_investigate_sanitizes_recommended_commands():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_investigate",
            {"tree_id": "revenue", "period": "last 7 days"},
            client=client,
            config=CONFIG,
        )
    )
    step = result["agent"]["recommended_next_steps"][0]
    assert step["command"].startswith("qluent rca analyze revenue --metric orders")
    assert "Converted from compare" in step["why"]


def test_dispatch_deep_dive_iterates_all_trees_when_none_specified():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_deep_dive",
            {"period": "last 7 days"},
            client=client,
            config=CONFIG,
        )
    )
    assert result["trees_requested"] == ["revenue"]
    assert "revenue" in result["trees"]
    assert result["errors"] == {}
    step = result["trees"]["revenue"]["agent"]["recommended_next_steps"][0]
    assert step["command"].startswith("qluent rca analyze revenue --metric orders")


def test_dispatch_deep_dive_rejects_unknown_tree_ids():
    client = FakeClient()
    try:
        asyncio.run(
            dispatch_tool(
                "qluent_deep_dive",
                {"tree_ids": ["does_not_exist"], "period": "last 7 days"},
                client=client,
                config=CONFIG,
            )
        )
    except ValueError as exc:
        assert "Unknown tree" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown tree id")


def test_dispatch_rca_analyze_forwards_metric():
    client = FakeClient()
    asyncio.run(
        dispatch_tool(
            "qluent_rca_analyze",
            {"tree_id": "revenue", "metric": "orders", "period": "last 7 days"},
            client=client,
            config=CONFIG,
        )
    )
    kwargs = client.calls[0][2]
    # metric now travels inside the typed params object.
    assert kwargs["params"].metric == "orders"


def test_dispatch_rca_analyze_returns_enriched_contract():
    """MCP must surface the enriched RCA contract, just like the CLI does.
    Provenance/schema_version cannot be skipped at the dispatch layer."""
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_rca_analyze",
            {"tree_id": "revenue", "period": "last 7 days"},
            client=client,
            config=CONFIG,
        )
    )
    assert result["schema_version"] == "qluent.rca.v1"
    assert result["contract_kind"] == "deterministic_rca"
    assert result["provenance"]["project_uuid"] == "project-123"


def test_dispatch_elasticity_attaches_provenance():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_elasticity",
            {
                "tree_id": "revenue",
                "outcome": "net_revenue",
                "lever": "orders",
                "dimension": "region",
                "period": "last 7 days",
            },
            client=client,
            config=CONFIG,
        )
    )
    assert result["contract_kind"] == "elasticity_analysis"
    assert result["provenance"]["project_uuid"] == "project-123"
    assert result["outcome"] == "net_revenue"
    assert result["lever"] == "orders"


def test_dispatch_suggestions_filters_by_tree_id():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_suggestions",
            {"tree_id": "revenue"},
            client=client,
            config=CONFIG,
        )
    )
    assert result["suggestions"]
    assert all(item["tree_id"] == "revenue" for item in result["suggestions"])


def test_dispatch_suggestions_for_unknown_tree_returns_empty():
    client = FakeClient()
    result = asyncio.run(
        dispatch_tool(
            "qluent_suggestions",
            {"tree_id": "missing"},
            client=client,
            config=CONFIG,
        )
    )
    assert result == {"suggestions": []}


def test_dispatch_unknown_tool_raises():
    client = FakeClient()
    try:
        asyncio.run(
            dispatch_tool("qluent_does_not_exist", {}, client=client, config=CONFIG)
        )
    except ValueError as exc:
        assert "Unknown tool" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown tool")


def test_build_server_registers_all_tools():
    server = build_server()
    # The lowlevel Server caches tool definitions on first list_tools call. We
    # exercise the registered handler directly to confirm every tool is
    # advertised over the wire.
    from mcp import types

    list_handler = server.request_handlers[types.ListToolsRequest]
    result = asyncio.run(list_handler(types.ListToolsRequest(method="tools/list")))
    advertised = {tool.name for tool in result.root.tools}
    assert advertised == set(HANDLERS)


def test_call_tool_handler_invokes_qluent_client_end_to_end(monkeypatch):
    """Smoke test: the registered call_tool handler calls the qluent client
    and returns a JSON-serialized payload as TextContent."""
    monkeypatch.setattr("qluent_cli.mcp_server.load_config", lambda: CONFIG)
    monkeypatch.setattr("qluent_cli.mcp_server.QluentClient", FakeClient)

    from mcp import types

    server = build_server()
    call_handler = server.request_handlers[types.CallToolRequest]

    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="qluent_list_trees", arguments={}),
    )
    server_result = asyncio.run(call_handler(request))
    call_result = server_result.root
    assert call_result.isError in (False, None)
    assert call_result.content
    text = call_result.content[0].text
    payload = json.loads(text)
    assert payload == TREE_DATA


def test_call_tool_handler_returns_setup_errors_as_text(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.mcp_server.load_config",
        lambda: (_ for _ in ()).throw(SystemExit("No API key configured.")),
    )

    from mcp import types

    server = build_server()
    call_handler = server.request_handlers[types.CallToolRequest]

    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="qluent_list_trees", arguments={}),
    )
    server_result = asyncio.run(call_handler(request))
    call_result = server_result.root
    assert call_result.content[0].text == "Error: No API key configured."


def test_qluent_mcp_serve_command_is_registered():
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_qluent_mcp_serve_invokes_serve_stdio(monkeypatch):
    called: dict[str, bool] = {}

    async def fake_serve():
        called["ok"] = True

    monkeypatch.setattr("qluent_cli.mcp_server.serve_stdio", fake_serve)

    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "serve"])
    assert result.exit_code == 0, result.output
    assert called == {"ok": True}
