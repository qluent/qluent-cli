#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_DIR="$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  scripts/local_smoke_test.sh

Optional environment variables:
  QLUENT_TEST_API_KEY       API key for a real API smoke test
  QLUENT_TEST_PROJECT_UUID  Project UUID for a real API smoke test
  QLUENT_TEST_USER_EMAIL    User email for a real API smoke test
  QLUENT_TEST_URL           API base URL (default: https://api.app-development.qluent.com)
  QLUENT_TEST_TREE_ID       Optional tree id for an extra trend smoke test
  QLUENT_SMOKE_NPM=1        Also test the local npm wrapper install in an isolated prefix

What it does:
  1. Builds the current-platform standalone binary with PyInstaller
  2. Runs '--help'
  3. Runs 'claude init' in a temp workspace
  4. Optionally configures the CLI and calls the live API
  5. Optionally tests the npm wrapper without touching your global npm prefix
EOF
}

if [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

platform_name() {
  case "$(uname -s)" in
    Darwin) echo "darwin" ;;
    Linux) echo "linux" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *) echo "Unsupported platform: $(uname -s)" >&2; exit 1 ;;
  esac
}

arch_name() {
  case "$(uname -m)" in
    arm64|aarch64) echo "arm64" ;;
    x86_64|amd64) echo "x64" ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
  esac
}

PLATFORM="$(platform_name)"
ARCH="$(arch_name)"
EXTENSION=""
if [[ "$PLATFORM" == "windows" ]]; then
  EXTENSION=".exe"
fi

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/qluent-smoke.XXXXXX")"
TMP_HOME="$TMP_ROOT/home"
TMP_WORKDIR="$TMP_ROOT/work"
mkdir -p "$TMP_HOME" "$TMP_WORKDIR"

echo "==> Building standalone binary"
(
  cd "$CLI_DIR"
  uv run --extra build python -m qluent_cli.build_binary
)

BINARY_PATH="$CLI_DIR/dist/binaries/qluent-${PLATFORM}-${ARCH}${EXTENSION}"
if [[ ! -x "$BINARY_PATH" ]]; then
  echo "Binary not found: $BINARY_PATH" >&2
  exit 1
fi

echo "==> Binary built at: $BINARY_PATH"
echo "==> Temp workspace: $TMP_ROOT"

echo "==> Smoke: --help"
"$BINARY_PATH" --help >/dev/null

echo "==> Smoke: claude init"
(
  cd "$TMP_WORKDIR"
  HOME="$TMP_HOME" "$BINARY_PATH" claude init >/dev/null
)

if [[ -n "${QLUENT_TEST_API_KEY:-}" && -n "${QLUENT_TEST_PROJECT_UUID:-}" && -n "${QLUENT_TEST_USER_EMAIL:-}" ]]; then
  TEST_URL="${QLUENT_TEST_URL:-https://api.app-development.qluent.com}"

  echo "==> Smoke: config + live API"
  HOME="$TMP_HOME" "$BINARY_PATH" config \
    --api-key "$QLUENT_TEST_API_KEY" \
    --project "$QLUENT_TEST_PROJECT_UUID" \
    --email "$QLUENT_TEST_USER_EMAIL" \
    --url "$TEST_URL" \
    >/dev/null

  HOME="$TMP_HOME" "$BINARY_PATH" trees list >/dev/null

  if [[ -n "${QLUENT_TEST_TREE_ID:-}" ]]; then
    HOME="$TMP_HOME" "$BINARY_PATH" trees trend "$QLUENT_TEST_TREE_ID" --periods 2 --grain week >/dev/null
  fi
else
  echo "==> Skipping live API smoke test"
  echo "    Set QLUENT_TEST_API_KEY, QLUENT_TEST_PROJECT_UUID, and QLUENT_TEST_USER_EMAIL to enable it"
fi

if [[ "${QLUENT_SMOKE_NPM:-0}" == "1" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found; cannot run npm smoke test" >&2
    exit 1
  fi

  echo "==> Smoke: local npm wrapper"
  NPM_STAGE="$TMP_ROOT/npm-stage"
  NPM_PREFIX="$TMP_ROOT/npm-prefix"
  cp -R "$CLI_DIR/npm" "$NPM_STAGE"
  cp "$BINARY_PATH" "$NPM_STAGE/bin/qluent${EXTENSION}"
  chmod +x "$NPM_STAGE/bin/qluent${EXTENSION}"

  QLUENT_SKIP_DOWNLOAD=1 npm install --global --prefix "$NPM_PREFIX" "$NPM_STAGE" >/dev/null
  "$NPM_PREFIX/bin/qluent" --help >/dev/null
fi

echo "==> Done"
echo "    Binary: $BINARY_PATH"
echo "    Temp HOME: $TMP_HOME"
echo "    Temp workdir: $TMP_WORKDIR"
