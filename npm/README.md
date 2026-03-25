# `@qluent/cli`

This npm package installs the platform-specific `qluent` binary.

## Install

```bash
npm install -g @qluent/cli
```

## First run

```bash
qluent setup
```

## Distribution host

By default the installer downloads binaries from:

```text
https://downloads.qluent.io/cli/v<VERSION>/
```

Override for testing or private staging:

```bash
QLUENT_CLI_DIST_BASE_URL=https://your-staging-host npm install -g @qluent/cli
```

Or point directly at one binary:

```bash
QLUENT_CLI_BIN_URL=https://your-host/qluent-darwin-arm64 npm install -g @qluent/cli
```
