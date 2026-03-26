# `@qluent/cli`

This npm package installs the platform-specific `qluent` binary.
Downloads must use HTTPS by default, and the installer verifies each binary against a `.sha256` checksum file before installation.

## Install

```bash
npm install -g @qluent/cli
```

## First run

```bash
qluent setup
```

This defaults to the Qluent test environment at `https://app-development.qluent.com`.
For local backend development, use:

```bash
qluent setup --local
```

## Distribution host

By default the installer downloads binaries from:

```text
https://github.com/qluent/qluent-cli/releases/download/v<VERSION>/
```

Override for testing or private staging:

```bash
QLUENT_CLI_DIST_BASE_URL=https://your-staging-host npm install -g @qluent/cli
```

Or point directly at one binary:

```bash
QLUENT_CLI_BIN_URL=https://your-host/qluent-darwin-arm64 npm install -g @qluent/cli
```

For local development only, you can allow insecure `http://` download URLs with:

```bash
QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD=1 npm install -g @qluent/cli
```
