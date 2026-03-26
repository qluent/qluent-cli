const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const {
  MAX_BINARY_SIZE,
  MAX_CHECKSUM_SIZE,
  allowInsecureDownload,
  assertSecureUrl,
  download,
  downloadText,
  installBinary,
  parseChecksumFile,
  platformArtifact,
  resolveChecksumUrl,
  resolveDownloadUrl,
  sha256File,
  verifyFileChecksum,
} = require("../lib/installer");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "qluent-test-"));
}

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

/** Spin up a throwaway HTTP server.  Returns { url, close, setHandler }. */
async function createTestServer() {
  let handler = (_req, res) => {
    res.writeHead(404);
    res.end();
  };
  const server = http.createServer((req, res) => handler(req, res));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}`,
    close: () => server.close(),
    setHandler: (fn) => {
      handler = fn;
    },
  };
}

/** Env object that allows insecure downloads (needed for local HTTP server). */
function insecureEnv(extra = {}) {
  return { QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "1", ...extra };
}

/** A silent logger that captures messages. */
function captureLogger() {
  const messages = [];
  return {
    messages,
    log: (msg) => messages.push(msg),
  };
}

// ---------------------------------------------------------------------------
// Original unit tests
// ---------------------------------------------------------------------------

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
  const tempDir = makeTempDir();
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

// ---------------------------------------------------------------------------
// Size limit tests
// ---------------------------------------------------------------------------

test("download rejects when response exceeds maxSize", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const dest = path.join(tempDir, "too-large");

  server.setHandler((_req, res) => {
    res.writeHead(200);
    // Send 2 KB when limit is 1 KB
    res.end(Buffer.alloc(2048, 0x41));
  });

  try {
    await assert.rejects(
      () => download(server.url + "/big", dest, { env: insecureEnv(), maxSize: 1024 }),
      /exceeded maximum size/
    );
    // Partial file must be cleaned up
    assert.equal(fs.existsSync(dest), false);
  } finally {
    server.close();
  }
});

test("download succeeds when response is within maxSize", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const dest = path.join(tempDir, "ok-size");

  const body = Buffer.from("small payload");
  server.setHandler((_req, res) => {
    res.writeHead(200);
    res.end(body);
  });

  try {
    await download(server.url + "/ok", dest, {
      env: insecureEnv(),
      maxSize: 1024 * 1024,
    });
    assert.deepEqual(fs.readFileSync(dest), body);
  } finally {
    server.close();
  }
});

test("downloadText rejects when response exceeds maxSize", async () => {
  const server = await createTestServer();

  server.setHandler((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("x".repeat(2048));
  });

  try {
    await assert.rejects(
      () => downloadText(server.url + "/big", { env: insecureEnv(), maxSize: 512 }),
      /exceeded maximum size/
    );
  } finally {
    server.close();
  }
});

test("downloadText succeeds within maxSize", async () => {
  const server = await createTestServer();
  const payload = "a]".repeat(32);

  server.setHandler((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end(payload);
  });

  try {
    const text = await downloadText(server.url + "/small", {
      env: insecureEnv(),
      maxSize: 4096,
    });
    assert.equal(text, payload);
  } finally {
    server.close();
  }
});

test("MAX_BINARY_SIZE and MAX_CHECKSUM_SIZE have sane defaults", () => {
  assert.equal(MAX_BINARY_SIZE, 200 * 1024 * 1024);
  assert.equal(MAX_CHECKSUM_SIZE, 1024);
});

// ---------------------------------------------------------------------------
// Download rejects non-200 status codes
// ---------------------------------------------------------------------------

test("download rejects on HTTP 404", async () => {
  const server = await createTestServer();
  const dest = path.join(makeTempDir(), "missing");

  server.setHandler((_req, res) => {
    res.writeHead(404);
    res.end("not found");
  });

  try {
    await assert.rejects(
      () => download(server.url + "/missing", dest, { env: insecureEnv() }),
      /Download failed with status 404/
    );
  } finally {
    server.close();
  }
});

test("download rejects after too many redirects", async () => {
  const server = await createTestServer();
  const dest = path.join(makeTempDir(), "loop");

  server.setHandler((_req, res) => {
    res.writeHead(302, { Location: server.url + "/loop" });
    res.end();
  });

  try {
    await assert.rejects(
      () =>
        download(server.url + "/loop", dest, {
          env: insecureEnv(),
          redirectsRemaining: 2,
        }),
      /Too many redirects/
    );
  } finally {
    server.close();
  }
});

test("download follows redirects up to the limit", async () => {
  const server = await createTestServer();
  const dest = path.join(makeTempDir(), "redirected");
  const body = Buffer.from("final content");

  server.setHandler((req, res) => {
    if (req.url === "/step1") {
      res.writeHead(302, { Location: server.url + "/step2" });
      res.end();
    } else {
      res.writeHead(200);
      res.end(body);
    }
  });

  try {
    await download(server.url + "/step1", dest, { env: insecureEnv() });
    assert.deepEqual(fs.readFileSync(dest), body);
  } finally {
    server.close();
  }
});

// ---------------------------------------------------------------------------
// Write-then-rename (TOCTOU) tests
// ---------------------------------------------------------------------------

test("installBinary writes to .tmp first and renames on success", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");
  const binaryContent = Buffer.from("fake-binary-content");
  const checksum = sha256(binaryContent);
  const artifactName = platformArtifact({ platform: "darwin", arch: "arm64" });

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(`${checksum}  ${artifactName}\n`);
    } else {
      res.writeHead(200);
      res.end(binaryContent);
    }
  });

  try {
    const dest = await installBinary({
      version: "1.0.0",
      env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
      binDir,
      platform: "darwin",
      arch: "arm64",
      logger: captureLogger(),
    });

    // Final binary exists and is executable
    assert.ok(fs.existsSync(dest));
    const stat = fs.statSync(dest);
    assert.equal(stat.mode & 0o755, 0o755);

    // .tmp must not linger
    assert.equal(fs.existsSync(`${dest}.tmp`), false);

    // Content matches
    assert.deepEqual(fs.readFileSync(dest), binaryContent);
  } finally {
    server.close();
  }
});

test("installBinary cleans up .tmp and leaves no final binary on checksum mismatch", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end("0".repeat(64)); // wrong checksum
    } else {
      res.writeHead(200);
      res.end(Buffer.from("some binary"));
    }
  });

  try {
    await assert.rejects(
      () =>
        installBinary({
          version: "1.0.0",
          env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
          binDir,
          platform: "darwin",
          arch: "arm64",
          logger: captureLogger(),
        }),
      /Checksum mismatch/
    );

    // Neither .tmp nor final binary should exist
    const binaryName = "qluent";
    assert.equal(fs.existsSync(path.join(binDir, binaryName)), false);
    assert.equal(fs.existsSync(path.join(binDir, `${binaryName}.tmp`)), false);
  } finally {
    server.close();
  }
});

test("installBinary cleans up .tmp when checksum download fails", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      res.writeHead(404);
      res.end("not found");
    } else {
      res.writeHead(200);
      res.end(Buffer.from("binary payload"));
    }
  });

  try {
    await assert.rejects(
      () =>
        installBinary({
          version: "1.0.0",
          env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
          binDir,
          platform: "darwin",
          arch: "arm64",
          logger: captureLogger(),
        }),
      /Download failed with status 404/
    );

    assert.equal(fs.existsSync(path.join(binDir, "qluent")), false);
    assert.equal(fs.existsSync(path.join(binDir, "qluent.tmp")), false);
  } finally {
    server.close();
  }
});

test("temp file is written with mode 0o600 (not executable)", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");
  let observedTmpMode = null;

  const binaryContent = Buffer.from("check-mode");
  const checksum = sha256(binaryContent);
  const artifactName = platformArtifact({ platform: "linux", arch: "x64" });

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      // Before returning checksum, observe the .tmp file permissions
      const tmpPath = path.join(binDir, "qluent.tmp");
      if (fs.existsSync(tmpPath)) {
        observedTmpMode = fs.statSync(tmpPath).mode & 0o777;
      }
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(`${checksum}  ${artifactName}\n`);
    } else {
      res.writeHead(200);
      res.end(binaryContent);
    }
  });

  try {
    await installBinary({
      version: "1.0.0",
      env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
      binDir,
      platform: "linux",
      arch: "x64",
      logger: captureLogger(),
    });

    // The .tmp file should have been 0o600 when it existed
    assert.equal(observedTmpMode, 0o600);
  } finally {
    server.close();
  }
});

// ---------------------------------------------------------------------------
// Insecure download warning
// ---------------------------------------------------------------------------

test("installBinary logs a warning when QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD is set", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");
  const logger = captureLogger();

  const binaryContent = Buffer.from("warn-test");
  const checksum = sha256(binaryContent);
  const artifactName = platformArtifact({ platform: "darwin", arch: "arm64" });

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(`${checksum}  ${artifactName}\n`);
    } else {
      res.writeHead(200);
      res.end(binaryContent);
    }
  });

  try {
    await installBinary({
      version: "1.0.0",
      env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
      binDir,
      platform: "darwin",
      arch: "arm64",
      logger,
    });

    const warningMsg = logger.messages.find((m) => m.includes("WARNING"));
    assert.ok(warningMsg, "expected a WARNING message in the logs");
    assert.match(warningMsg, /QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD/);
    assert.match(warningMsg, /local development/);
  } finally {
    server.close();
  }
});

test("installBinary does not warn when QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD is not set", async () => {
  // We can't hit a real HTTPS server in unit tests, so just test the skip path
  const logger = captureLogger();

  await installBinary({
    version: "1.0.0",
    env: { QLUENT_SKIP_DOWNLOAD: "1" },
    logger,
  });

  const warningMsg = logger.messages.find((m) => m.includes("WARNING"));
  assert.equal(warningMsg, undefined, "should not log a WARNING");
});

// ---------------------------------------------------------------------------
// QLUENT_SKIP_DOWNLOAD
// ---------------------------------------------------------------------------

test("installBinary returns null when QLUENT_SKIP_DOWNLOAD=1", async () => {
  const logger = captureLogger();
  const result = await installBinary({
    version: "1.0.0",
    env: { QLUENT_SKIP_DOWNLOAD: "1" },
    logger,
  });

  assert.equal(result, null);
  assert.ok(logger.messages.some((m) => m.includes("Skipping")));
});

test("installBinary throws when version is missing", async () => {
  await assert.rejects(
    () => installBinary({ env: {} }),
    /version is required/
  );
});

// ---------------------------------------------------------------------------
// resolveDownloadUrl – env var overrides
// ---------------------------------------------------------------------------

test("resolveDownloadUrl uses QLUENT_CLI_BIN_URL when set", () => {
  const url = resolveDownloadUrl({
    env: { QLUENT_CLI_BIN_URL: "https://my-mirror.example.com/qluent-darwin-arm64" },
    version: "0.1.0",
    platform: "darwin",
    arch: "arm64",
  });
  assert.equal(url, "https://my-mirror.example.com/qluent-darwin-arm64");
});

test("resolveDownloadUrl rejects HTTP QLUENT_CLI_BIN_URL without insecure override", () => {
  assert.throws(
    () =>
      resolveDownloadUrl({
        env: { QLUENT_CLI_BIN_URL: "http://evil.example.com/qluent" },
        version: "0.1.0",
      }),
    /Refusing insecure download URL/
  );
});

test("resolveDownloadUrl requires a version", () => {
  assert.throws(
    () => resolveDownloadUrl({ env: {} }),
    /version is required/
  );
});

// ---------------------------------------------------------------------------
// platformArtifact edge cases
// ---------------------------------------------------------------------------

test("platformArtifact rejects unsupported platform", () => {
  assert.throws(
    () => platformArtifact({ platform: "freebsd", arch: "x64" }),
    /Unsupported platform/
  );
});

test("platformArtifact rejects unsupported arch", () => {
  assert.throws(
    () => platformArtifact({ platform: "linux", arch: "mips" }),
    /Unsupported platform/
  );
});

test("platformArtifact covers all supported combinations", () => {
  const expected = {
    "darwin-x64": "qluent-darwin-x64",
    "darwin-arm64": "qluent-darwin-arm64",
    "linux-x64": "qluent-linux-x64",
    "linux-arm64": "qluent-linux-arm64",
    "win32-x64": "qluent-windows-x64.exe",
    "win32-arm64": "qluent-windows-arm64.exe",
  };

  for (const [key, artifact] of Object.entries(expected)) {
    const [platform, arch] = key.split("-");
    assert.equal(platformArtifact({ platform, arch }), artifact);
  }
});

// ---------------------------------------------------------------------------
// parseChecksumFile edge cases
// ---------------------------------------------------------------------------

test("parseChecksumFile rejects empty content", () => {
  assert.throws(() => parseChecksumFile("", "qluent-darwin-arm64"), /empty/);
  assert.throws(() => parseChecksumFile("   \n\n  ", "qluent-darwin-arm64"), /empty/);
});

test("parseChecksumFile rejects content that doesn't match artifact", () => {
  assert.throws(
    () => parseChecksumFile(`${"a".repeat(64)}  wrong-artifact`, "qluent-darwin-arm64"),
    /Could not parse checksum/
  );
});

test("parseChecksumFile handles CRLF line endings", () => {
  const checksum = "d".repeat(64);
  const content = `${checksum}  qluent-linux-x64\r\n`;
  assert.equal(parseChecksumFile(content, "qluent-linux-x64"), checksum);
});

test("parseChecksumFile handles binary mode indicator (*)", () => {
  const checksum = "e".repeat(64);
  const content = `${checksum} *qluent-linux-x64`;
  assert.equal(parseChecksumFile(content, "qluent-linux-x64"), checksum);
});

test("parseChecksumFile normalizes uppercase hex to lowercase", () => {
  const upper = "ABCDEF".repeat(10) + "ABCD";
  assert.equal(
    parseChecksumFile(upper, "qluent-darwin-arm64"),
    upper.toLowerCase()
  );
});

// ---------------------------------------------------------------------------
// allowInsecureDownload
// ---------------------------------------------------------------------------

test("allowInsecureDownload returns false for empty env", () => {
  assert.equal(allowInsecureDownload({}), false);
});

test("allowInsecureDownload returns false for non-1 values", () => {
  assert.equal(allowInsecureDownload({ QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "true" }), false);
  assert.equal(allowInsecureDownload({ QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "yes" }), false);
  assert.equal(allowInsecureDownload({ QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "0" }), false);
});

test("allowInsecureDownload returns true only for exactly '1'", () => {
  assert.equal(allowInsecureDownload({ QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "1" }), true);
});

// ---------------------------------------------------------------------------
// assertSecureUrl edge cases
// ---------------------------------------------------------------------------

test("assertSecureUrl allows HTTP when insecure override is set", () => {
  const url = assertSecureUrl("http://localhost:9000/test", {
    env: { QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD: "1" },
  });
  assert.equal(url.protocol, "http:");
});

test("assertSecureUrl rejects non-http(s) protocols", () => {
  assert.throws(
    () => assertSecureUrl("ftp://files.example.com/qluent"),
    /Refusing insecure download URL/
  );
  assert.throws(
    () => assertSecureUrl("file:///etc/passwd"),
    /Refusing insecure download URL/
  );
});

// ---------------------------------------------------------------------------
// End-to-end installBinary with Windows naming
// ---------------------------------------------------------------------------

test("installBinary uses .exe suffix on win32", async () => {
  const server = await createTestServer();
  const tempDir = makeTempDir();
  const binDir = path.join(tempDir, "bin");
  const binaryContent = Buffer.from("win-binary");
  const checksum = sha256(binaryContent);
  const artifactName = platformArtifact({ platform: "win32", arch: "x64" });

  server.setHandler((req, res) => {
    if (req.url.endsWith(".sha256")) {
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end(`${checksum}  ${artifactName}\n`);
    } else {
      res.writeHead(200);
      res.end(binaryContent);
    }
  });

  try {
    const dest = await installBinary({
      version: "1.0.0",
      env: insecureEnv({ QLUENT_CLI_DIST_BASE_URL: server.url }),
      binDir,
      platform: "win32",
      arch: "x64",
      logger: captureLogger(),
    });

    assert.ok(dest.endsWith("qluent.exe"));
    assert.ok(fs.existsSync(dest));
    assert.equal(fs.existsSync(`${dest}.tmp`), false);
  } finally {
    server.close();
  }
});
