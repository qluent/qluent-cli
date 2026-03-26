const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  assertSecureUrl,
  parseChecksumFile,
  platformArtifact,
  resolveChecksumUrl,
  resolveDownloadUrl,
  sha256File,
  verifyFileChecksum,
} = require("../lib/installer");

test("resolveDownloadUrl uses the default HTTPS host", () => {
  const url = resolveDownloadUrl({
    env: {},
    version: "0.1.0",
    platform: "darwin",
    arch: "arm64",
  });

  assert.equal(
    url,
    "https://github.com/qluent/qluent-cli/releases/download/v0.1.0/qluent-darwin-arm64"
  );
});

test("resolveDownloadUrl rejects insecure HTTP URLs by default", () => {
  assert.throws(
    () =>
      resolveDownloadUrl({
        env: { QLUENT_CLI_DIST_BASE_URL: "http://localhost:9000/cli" },
        version: "0.1.0",
        platform: "darwin",
        arch: "arm64",
      }),
    /Refusing insecure download URL/
  );
});

test("resolveDownloadUrl allows insecure URLs only with the explicit dev override", () => {
  const url = resolveDownloadUrl({
    env: {
      QLUENT_CLI_DIST_BASE_URL: "http://localhost:9000/cli",
      QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "1",
    },
    version: "0.1.0",
    platform: "darwin",
    arch: "arm64",
  });

  assert.equal(url, "http://localhost:9000/cli/v0.1.0/qluent-darwin-arm64");
});

test("parseChecksumFile supports common sha256 formats", () => {
  assert.equal(
    parseChecksumFile(
      "a".repeat(64),
      "qluent-darwin-arm64"
    ),
    "a".repeat(64)
  );
  assert.equal(
    parseChecksumFile(
      `${"b".repeat(64)}  qluent-darwin-arm64`,
      "qluent-darwin-arm64"
    ),
    "b".repeat(64)
  );
  assert.equal(
    parseChecksumFile(
      `SHA256 (qluent-darwin-arm64) = ${"c".repeat(64)}`,
      "qluent-darwin-arm64"
    ),
    "c".repeat(64)
  );
});

test("resolveChecksumUrl appends .sha256", () => {
  assert.equal(
    resolveChecksumUrl(
      "https://github.com/qluent/qluent-cli/releases/download/v0.1.0/qluent-darwin-arm64"
    ),
    "https://github.com/qluent/qluent-cli/releases/download/v0.1.0/qluent-darwin-arm64.sha256"
  );
});

test("verifyFileChecksum validates the downloaded binary content", () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "qluent-installer-"));
  const filePath = path.join(tempDir, "qluent-darwin-arm64");
  fs.writeFileSync(filePath, "hello");

  const digest = sha256File(filePath);
  verifyFileChecksum(filePath, digest);
  assert.throws(() => verifyFileChecksum(filePath, "0".repeat(64)), /Checksum mismatch/);
});

test("platformArtifact matches the binary naming convention", () => {
  assert.equal(platformArtifact({ platform: "darwin", arch: "arm64" }), "qluent-darwin-arm64");
  assert.equal(platformArtifact({ platform: "win32", arch: "x64" }), "qluent-windows-x64.exe");
});

test("assertSecureUrl accepts HTTPS and rejects HTTP by default", () => {
  assert.equal(
    assertSecureUrl("https://github.com/qluent/qluent-cli/releases/download").toString(),
    "https://github.com/qluent/qluent-cli/releases/download"
  );
  assert.throws(
    () => assertSecureUrl("http://github.com/qluent/qluent-cli/releases/download"),
    /Refusing insecure download URL/
  );
});
