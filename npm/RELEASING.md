# Releasing `@qluent/cli`

This package is a thin npm installer for the platform-specific `qluent` binary.

## Overview

Release flow:

1. Build the standalone `qluent` binaries.
2. Publish them as GitHub Release assets for the matching tag.
3. Publish the npm package with the matching version.
4. Smoke-test `npm install -g @qluent/cli`.

The npm installer expects binaries at:

```text
https://github.com/qluent/qluent-cli/releases/download/v<VERSION>/
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

## Step 2: Publish GitHub Release assets

The release workflow publishes each binary and checksum file to the tag's GitHub Release.
For `v0.1.1`, the final URLs look like:

```text
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-darwin-arm64
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-linux-x64
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-windows-x64.exe
```

With checksum sidecars:

```text
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-darwin-arm64.sha256
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-linux-x64.sha256
https://github.com/qluent/qluent-cli/releases/download/v0.1.1/qluent-windows-x64.exe.sha256
```

The npm installer verifies each downloaded binary against its sidecar before installation.
If the workflow succeeds but no release appears, confirm the repository allows Actions to create releases.

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
QLUENT_CLI_DIST_BASE_URL=https://github.com/qluent/qluent-cli/releases/download npm install -g @qluent/cli
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

If the npm package is published but release assets are missing or broken:

1. unpublish or deprecate the npm version
2. fix and re-publish the GitHub Release assets
3. republish or cut a patch release

Keep the npm package version and release tag aligned.
