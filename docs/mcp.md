# MCP Server

`qluent mcp serve` runs a [Model Context Protocol](https://modelcontextprotocol.io)
server over stdio. It exposes the same client methods that back the `qluent`
CLI as MCP tools, so non-Claude agents (Codex CLI, Cursor, Continue, Zed, ...)
can call qluent without per-agent forks.

## Why

Today qluent integrates with AI agents through one path: a Claude Code plugin
that shells out to the CLI. The MCP server adds a second path that any
MCP-speaking client can use:

- One implementation, every MCP-capable agent.
- First-class typed tool calls instead of bash quoting around `--filter`/`--period`.
- Tool outputs are the existing `--json-output` contracts; no divergence.

The Claude Code plugin still works. This is additive.

## Configuration

The server reuses `~/.qluent/config.json`. Log in first with `qluent login`.
You can also override via env vars (`QLUENT_API_KEY`, `QLUENT_PROJECT_UUID`,
`QLUENT_USER_EMAIL`, `QLUENT_API_URL`, `QLUENT_CLIENT_SAFE`).

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.qluent]
command = "qluent"
args = ["mcp", "serve"]
env = { QLUENT_API_KEY = "qk_..." }
```

### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "qluent": {
      "command": "qluent",
      "args": ["mcp", "serve"]
    }
  }
}
```

### Claude Code (`~/.claude/mcp_servers.json`)

```json
{
  "mcpServers": {
    "qluent": {
      "command": "qluent",
      "args": ["mcp", "serve"]
    }
  }
}
```

## Tools

All tools accept date windows in one of two forms:

- `period`: natural-language string (e.g. `"last week"`, `"this month"`,
  `"last 30 days"`). Defaults to `"last 7 days"` when omitted.
- `current` + `compare`: explicit ISO ranges, each `"YYYY-MM-DD:YYYY-MM-DD"`.

### `qluent_list_trees`

List the metric trees in the connected project. No arguments.

### `qluent_get_tree`

Return the structure (nodes, formulas, metadata) of a single tree.

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | yes |

### `qluent_evaluate`

Evaluate a tree over a current and comparison window. Returns node values,
deltas, contributions, sensitivities, and elasticities.

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | yes |
| `period` / `current` / `compare` | string | window picker |

### `qluent_investigate`

Run the deterministic investigation bundle (evaluation + trend + RCA + agent
recommended next steps).

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | yes |
| `period` / `current` / `compare` | string | window picker |
| `trend_periods` | integer | default 4 |
| `trend_grain` | `"week" \| "month"` | default `"week"` |
| `trend_as_of` | string (`YYYY-MM-DD`) | optional |
| `segment_by` | `string[]` | optional |
| `filters` | `{[dimension]: string[]}` | optional |
| `compare_trees` | `string[]` | optional |
| `max_depth`, `max_branches`, `max_segments`, `min_contribution_share` | numbers | RCA tuning |

### `qluent_deep_dive`

Run investigations across many trees in parallel and bundle the results,
keyed by tree id. Same options as `qluent_investigate`, plus:

| Arg | Type | Required |
|-----|------|----------|
| `tree_ids` | `string[]` | optional; defaults to every tree |

### `qluent_rca_analyze`

Run deterministic root-cause analysis for a tree (or a single metric within
it).

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | yes |
| `metric` | string | optional; defaults to root |
| `period` / `current` / `compare` | string | window picker |
| `segment_by`, `filters`, `max_depth`, `max_branches`, `max_segments`, `min_contribution_share` | RCA tuning | optional |

### `qluent_elasticity`

Analyze observed elasticity between a lever metric and an outcome metric.

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | yes |
| `outcome` | string | yes |
| `lever` | string | yes |
| `dimension` | string | optional |
| `period` / `current` / `compare` | string | window picker |
| `filters` | `{[dimension]: string[]}` | optional |

### `qluent_suggestions`

Return project-specific example questions and matching CLI commands derived
deterministically from tree metadata.

| Arg | Type | Required |
|-----|------|----------|
| `tree_id` | string | optional; filters to one tree |

## Output shape

Every tool returns a JSON-serialized payload as a single `TextContent` block.
The payload is the same structure the CLI emits with `--json-output`, so any
existing parsing logic continues to work over MCP.
