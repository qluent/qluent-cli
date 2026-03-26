# Qluent CLI

`qluent` is a client-facing CLI for deterministic metric-tree analysis and root-cause analysis.
This README is written for the standalone `qluent-cli` repository layout.

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

The default test environment is `https://app-development.qluent.com`.
For local backend development, run:

```bash
qluent setup --local
```

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
qluent trees match "Why did revenue drop last week?"
qluent trees trend revenue --periods 4 --grain week
qluent trees investigate revenue --period "last week"
qluent rca analyze revenue --period "last week"
```

## Internal / Direct Python Install

If you are installing from source instead of the npm distribution, run these commands from the
CLI repo root:

```bash
uv build
pipx install dist/qluent_cli-0.1.1-py3-none-any.whl
```

## Building Release Binaries

For the npm installer, build a standalone binary on each target platform from the CLI repo root:

```bash
uv run --extra build python -m qluent_cli.build_binary
```

That writes a platform-specific artifact to:

```text
dist/binaries/
```

Examples:

```text
qluent-darwin-arm64
qluent-linux-x64
qluent-windows-x64.exe
```

It also writes a matching SHA-256 sidecar file for each artifact:

```text
qluent-darwin-arm64.sha256
```

PyInstaller builds for the current OS/architecture, so run the build once per target platform or use CI runners for each platform.

## Local End-To-End Smoke Test

To build the current-platform binary and smoke-test it in an isolated temp home directory:

```bash
scripts/local_smoke_test.sh
```

To also test the npm wrapper locally:

```bash
QLUENT_SMOKE_NPM=1 scripts/local_smoke_test.sh
```

To include a real API smoke test:

```bash
QLUENT_TEST_API_KEY=qk_... \
QLUENT_TEST_PROJECT_UUID=<PROJECT_UUID> \
QLUENT_TEST_USER_EMAIL=you@example.com \
QLUENT_TEST_URL=https://app-development.qluent.com \
QLUENT_TEST_TREE_ID=revenue \
scripts/local_smoke_test.sh
```

## Publishing

The npm wrapper lives in [npm](./npm). It is designed to download platform-specific release binaries from your distribution host.
It requires HTTPS downloads by default and verifies each binary against its `.sha256` sidecar before installation.
The default distribution host is the GitHub Releases page for `qluent/qluent-cli`.
