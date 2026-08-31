# Qluent CLI — Development Guide

This is the source repo for the `qluent` CLI tool. For the Claude Code plugin
(commands, agents, hooks), see [qluent-plugin-cc](https://github.com/qluent/qluent-plugin-cc).

## Project structure

```
src/qluent_cli/
├── main.py                # CLI entry point (see `qluent --help` for the full command list)
├── trees.py               # `qluent trees` command group (list, match, get, validate, evaluate, trend, compare, investigate)
├── rca.py                 # `qluent rca` command group (analyze)
├── elasticity.py          # `qluent elasticity` command
├── sessions.py            # Investigation session persistence
├── suggestions.py         # Tree/period suggestions used by investigate
├── plugin.py              # Plugin hook registration
├── mcp_server.py          # MCP server adapter
├── client.py              # HTTP client (httpx) for the Qluent API
├── config.py              # Config file management (~/.qluent/config.json)
├── auth.py                # Browser-based SSO login flow
├── output.py              # Stdout/stderr helpers
├── tree_contracts.py      # Typed contract for `tree query` agent output
├── rca_contracts.py       # Typed contract for RCA agent output
├── contract_helpers.py    # Shared TypedDicts (Provenance, Window, WindowMetadata) + helpers
├── formatters/            # Human-readable output formatting (one module per result kind)
│   ├── __init__.py        # Re-exports the public format_* functions
│   ├── _common.py         # Shared number/date primitives
│   ├── trees.py           # format_tree_list, format_tree_detail
│   ├── evaluation.py      # format_evaluation, format_levers
│   ├── elasticity.py      # format_elasticity
│   ├── rca.py             # format_root_cause
│   ├── validation.py      # format_tree_validation
│   ├── trend.py           # format_trend
│   ├── comparison.py      # format_comparison
│   └── investigation.py   # format_investigation (composes the others)
├── dates.py               # Natural-language date parsing
├── utils.py               # Shared helpers (parse_filters, format_step_error, resolve_date_args)
├── agent_instructions.md  # Embedded template for `qluent claude init`
└── build_binary.py        # PyInstaller binary compilation

npm/                 # NPM package (@qluent/cli) — Node.js shim that spawns the Python binary
tests/               # pytest test suite
scripts/             # bump_version.py (version manifests) and local_smoke_test.sh
Makefile             # Developer and release entry points
```

## Running tests

```bash
make test                                              # pytest + npm installer tests
uv run pytest
uv run pytest tests/test_trees.py -k "test_evaluate"   # single test
```

CI runs pytest, the npm installer tests, and a native binary build on every PR.

## Building binaries

```bash
make binary   # or: uv run python -m qluent_cli.build_binary
# Output: dist/binaries/qluent-<platform>-<arch>
```

PyInstaller builds for the current platform only. CI builds all five targets the
npm installer can resolve.

## Releasing

The version lives in four files. Never edit them by hand — `scripts/bump_version.py`
is the only writer, and CI fails on drift.

```bash
make bump VERSION=0.1.21     # pyproject, __init__.py, npm/package.json, uv.lock
git commit -am "Release 0.1.21"
# PR, merge, pull main, then:
make release VERSION=0.1.21  # verifies, tests, tags, pushes
```

The tag triggers build → sign → GitHub release → npm publish (OIDC trusted
publishing, no token). See [npm/RELEASING.md](npm/RELEASING.md) for the full
flow, the cross-repo ordering rule with the plugin, and rollback.

## CLI architecture

- **Click** commands: `trees`, `query`, `catalog`, `plan`, `rca`, `elasticity`,
  `suggestions`, `runs`, `agents`, `claude`, `mcp`, `config`, `setup`, `login`,
  `status`/`whoami`, `instructions`
- **httpx** client with API key auth (`X-API-Key` header)
- Config stored at `~/.qluent/config.json` (api_key, api_url, project_uuid, user_email, client_safe)
- `--json-output` flag on all tree/rca commands for structured output
- `--client-safe` mode redacts formulas and SQL contract details
