# Qluent CLI — Development Guide

This is the source repo for the `qluent` CLI tool. For the Claude Code plugin
(commands, agents, hooks), see [qluent-plugin-cc](https://github.com/qluent/qluent-plugin-cc).

## Project structure

```
src/qluent_cli/
├── main.py                # CLI entry point (Click groups: trees, rca, config, setup, login)
├── trees.py               # `qluent trees` command group (list, match, get, validate, evaluate, trend, compare, investigate)
├── rca.py                 # `qluent rca` command group (analyze)
├── utils.py               # Shared helpers (parse_filters, format_step_error, resolve_date_args)
├── client.py              # HTTP client (httpx) for the Qluent API
├── config.py              # Config file management (~/.qluent/config.json)
├── auth.py                # Browser-based SSO login flow
├── matching.py            # Tree matching / question-to-tree NLP
├── formatters.py          # Human-readable output formatting
├── dates.py               # Natural-language date parsing
├── claude_instructions.md # Embedded CLAUDE.md template for `qluent claude init`
└── build_binary.py        # PyInstaller binary compilation

npm/                 # NPM package (@qluent/cli) — Node.js shim that spawns the Python binary
tests/               # pytest test suite
scripts/             # Smoke tests and release helpers
```

## Running tests

```bash
uv run pytest
uv run pytest tests/test_trees.py -k "test_evaluate"   # single test
```

## Building binaries

```bash
uv run python -m qluent_cli.build_binary
# Output: dist/binaries/qluent-<platform>-<arch>
```

## CLI architecture

- **Click** groups: `cli` → `trees`, `rca`, `config`, `setup`, `login`, `claude`, `instructions`
- **httpx** client with API key auth (`X-API-Key` header)
- Config stored at `~/.qluent/config.json` (api_key, api_url, project_uuid, user_email, client_safe)
- `--json-output` flag on all tree/rca commands for structured output
- `--client-safe` mode redacts formulas and SQL contract details
