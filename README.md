# Qluent CLI

`qluent` is a client-facing CLI for deterministic metric-tree analysis and root-cause analysis.

## Client Install

The intended client install path is npm:

```bash
npm install -g @qluent/cli
```

Or without a global install:

```bash
npx @qluent/cli setup
```

After install:

```bash
qluent setup
```

That walks the user through:
- API key
- project UUID
- email
- API URL
- generating `CLAUDE.md`

Hosted API URLs default to client-safe mode automatically. Localhost URLs default to full-access mode for development.

## Claude Code Setup

The easiest path is:

```bash
qluent setup
```

Or, if config is already present:

```bash
qluent claude init
```

That writes `CLAUDE.md` in the current directory so Claude Code can use the CLI correctly.

## First Commands

```bash
qluent trees list
qluent trees trend revenue --periods 4 --grain week
qluent rca analyze revenue --period "last week"
```

## Internal / Direct Python Install

If you are installing from this repo instead of the npm distribution:

```bash
cd cli
uv build
pipx install dist/qluent_cli-0.1.0-py3-none-any.whl
```

## Publishing

The npm wrapper lives in [npm](./npm). It is designed to download platform-specific release binaries from your distribution host.
