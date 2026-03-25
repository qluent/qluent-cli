# Releasing `@qluent/cli`

This package is a thin npm installer for the platform-specific `qluent` binary.

## Overview

Release flow:

1. Build the standalone `qluent` binaries.
2. Upload them to the binary distribution host.
3. Publish the npm package with the matching version.
4. Smoke-test `npm install -g @qluent/cli`.

The npm installer expects binaries at:

```text
https://downloads.qluent.io/cli/v<VERSION>/
```

With these names:

```text
qluent-darwin-arm64
qluent-darwin-x64
qluent-linux-x64
qluent-linux-arm64
qluent-windows-x64.exe
```

## Step 1: Build binaries

Build one binary per target platform. Recommended targets:

- macOS arm64
- macOS x64
- Linux x64
- Linux arm64
- Windows x64

From the `qluent-cli` repo root:

```bash
uv run --extra build python -m qluent_cli.build_binary
```

That produces a correctly named artifact in:

```text
dist/binaries/
```

Examples:

```text
qluent-darwin-arm64
qluent-linux-x64
qluent-windows-x64.exe
```

PyInstaller builds for the current OS/architecture only, so run the build once per target platform or use native CI runners.

You can also use the standalone GitHub Actions workflow in [.github/workflows/qluent-cli-binaries.yml](../.github/workflows/qluent-cli-binaries.yml) to build native artifacts on macOS, Linux, and Windows runners.

## Step 2: Upload binaries

Upload each binary to:

```text
https://downloads.qluent.io/cli/v0.1.0/
```

Example final URLs:

```text
https://downloads.qluent.io/cli/v0.1.0/qluent-darwin-arm64
https://downloads.qluent.io/cli/v0.1.0/qluent-linux-x64
https://downloads.qluent.io/cli/v0.1.0/qluent-windows-x64.exe
```

Upload the matching checksum sidecars too:

```text
https://downloads.qluent.io/cli/v0.1.0/qluent-darwin-arm64.sha256
https://downloads.qluent.io/cli/v0.1.0/qluent-linux-x64.sha256
https://downloads.qluent.io/cli/v0.1.0/qluent-windows-x64.exe.sha256
```

The npm installer verifies each downloaded binary against its sidecar before installation.

## Step 3: Publish npm package

From [npm](./):

```bash
npm publish --access restricted
```

If you publish to a private registry:

```bash
npm publish --registry https://<your-registry>
```

## Step 4: Smoke test

Use a clean machine or container and run:

```bash
npm install -g @qluent/cli
qluent --help
qluent setup
```

Also verify override paths:

```bash
QLUENT_CLI_DIST_BASE_URL=https://your-staging-host npm install -g @qluent/cli
```

and:

```bash
QLUENT_CLI_BIN_URL=https://your-host/qluent-darwin-arm64 npm install -g @qluent/cli
```

If you need to test an insecure local `http://` host during development, use:

```bash
QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD=1 QLUENT_CLI_DIST_BASE_URL=http://localhost:9000 npm install -g @qluent/cli
```

## Rollback

If the npm package is published but binaries are missing or broken:

1. unpublish or deprecate the npm version
2. fix and re-upload binaries
3. republish or cut a patch release

Keep the npm package version and binary folder version aligned.
