const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

const {
  belongsToThisPackage,
  detectVersionManager,
  executableNames,
  formatShadowWarning,
  isExecutableFile,
  npmBinDirs,
  pathEntries,
  readVersion,
  resolveFirstOnPath,
  warnIfShadowed,
} = require("../lib/shadow-check");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "qluent-shadow-test-"));
}

/** Create an executable stub named `qluent` inside `directory`. */
function makeFakeBinary(directory, name = "qluent") {
  fs.mkdirSync(directory, { recursive: true });
  const target = path.join(directory, name);
  fs.writeFileSync(target, "#!/bin/sh\necho fake\n", { mode: 0o755 });
  return target;
}

function collectingLogger() {
  const messages = [];
  return {
    messages,
    warn: (message) => messages.push(message),
    log: (message) => messages.push(message),
  };
}

// ---------------------------------------------------------------------------
// PATH parsing
// ---------------------------------------------------------------------------

test("pathEntries splits on the platform delimiter and drops empties", () => {
  assert.deepEqual(
    pathEntries({ env: { PATH: "/a::/b:/c" }, platform: "linux" }),
    ["/a", "/b", "/c"]
  );
  assert.deepEqual(
    pathEntries({ env: { PATH: 'C:\\a;"C:\\b";' }, platform: "win32" }),
    ["C:\\a", "C:\\b"]
  );
});

test("pathEntries returns nothing when PATH is unset", () => {
  assert.deepEqual(pathEntries({ env: {}, platform: "linux" }), []);
});

test("executableNames applies PATHEXT on Windows only", () => {
  assert.deepEqual(executableNames("qluent", { env: {}, platform: "linux" }), [
    "qluent",
  ]);
  assert.deepEqual(
    executableNames("qluent", { env: { PATHEXT: ".EXE;.CMD" }, platform: "win32" }),
    ["qluent.exe", "qluent.cmd", "qluent"]
  );
});

test("isExecutableFile rejects directories and non-executable files", () => {
  const dir = makeTempDir();
  const plain = path.join(dir, "plain");
  fs.writeFileSync(plain, "hi", { mode: 0o644 });

  assert.equal(isExecutableFile(dir, { platform: "linux" }), false);
  assert.equal(isExecutableFile(plain, { platform: "linux" }), false);
  assert.equal(
    isExecutableFile(path.join(dir, "missing"), { platform: "linux" }),
    false
  );
  assert.equal(isExecutableFile(makeFakeBinary(dir), { platform: "linux" }), true);
});

// ---------------------------------------------------------------------------
// Resolution order
// ---------------------------------------------------------------------------

test("resolveFirstOnPath reports a foreign qluent that comes first", () => {
  const root = makeTempDir();
  const other = path.join(root, "local-bin");
  const npmBin = path.join(root, "npm-bin");
  fs.mkdirSync(npmBin, { recursive: true });
  const shadowing = makeFakeBinary(other);

  const found = resolveFirstOnPath("qluent", {
    env: { PATH: [other, npmBin].join(path.delimiter) },
    platform: "linux",
    ownDirs: [npmBin],
  });

  assert.equal(found.kind, "foreign");
  assert.equal(found.resolved, shadowing);
});

test("resolveFirstOnPath is satisfied by our own bin dir coming first", () => {
  // npm links the shim after postinstall runs, so an empty own directory that
  // wins on PATH must not be reported as shadowed.
  const root = makeTempDir();
  const other = path.join(root, "local-bin");
  const npmBin = path.join(root, "npm-bin");
  fs.mkdirSync(npmBin, { recursive: true });
  makeFakeBinary(other);

  const found = resolveFirstOnPath("qluent", {
    env: { PATH: [npmBin, other].join(path.delimiter) },
    platform: "linux",
    ownDirs: [npmBin],
  });

  assert.equal(found.kind, "ours");
  assert.equal(found.resolved, null);
});

test("resolveFirstOnPath reports none when nothing matches", () => {
  const root = makeTempDir();
  const found = resolveFirstOnPath("qluent", {
    env: { PATH: root },
    platform: "linux",
    ownDirs: [],
  });

  assert.equal(found.kind, "none");
});

test("npmBinDirs derives the global bin from npm_config_prefix", () => {
  assert.equal(
    npmBinDirs({ env: { npm_config_prefix: "/opt/node" }, platform: "linux" })[0],
    path.join("/opt/node", "bin")
  );
  assert.equal(
    npmBinDirs({ env: { npm_config_prefix: "C:\\node" }, platform: "win32" })[0],
    "C:\\node"
  );
});

// ---------------------------------------------------------------------------
// Ownership
// ---------------------------------------------------------------------------

test("belongsToThisPackage accepts paths inside the package", () => {
  const packageDir = makeTempDir();
  const binary = makeFakeBinary(path.join(packageDir, "bin"));

  assert.equal(belongsToThisPackage(binary, { packageDir }), true);
});

test("belongsToThisPackage accepts a generated wrapper naming the package", () => {
  const packageDir = makeTempDir();
  const elsewhere = makeTempDir();
  const wrapper = path.join(elsewhere, "qluent.cmd");
  fs.writeFileSync(wrapper, '@node "%~dp0\\node_modules\\@qluent/cli\\bin\\qluent.js"');

  assert.equal(belongsToThisPackage(wrapper, { packageDir }), true);
});

test("belongsToThisPackage rejects an unrelated binary", () => {
  const packageDir = makeTempDir();
  const binary = makeFakeBinary(makeTempDir());

  assert.equal(belongsToThisPackage(binary, { packageDir }), false);
  assert.equal(belongsToThisPackage(null, { packageDir }), false);
});

// ---------------------------------------------------------------------------
// Version probing and messaging
// ---------------------------------------------------------------------------

test("readVersion parses the version out of --version output", () => {
  const version = readVersion("/somewhere/qluent", {
    spawn: (executable, args) => {
      assert.deepEqual(args, ["--version"]);
      return { status: 0, stdout: "qluent, version 0.1.15\n", stderr: "" };
    },
  });

  assert.equal(version, "0.1.15");
});

test("readVersion returns null when the executable cannot be run", () => {
  assert.equal(
    readVersion("/somewhere/qluent", {
      spawn: () => ({ error: new Error("ENOENT"), status: null }),
    }),
    null
  );
  assert.equal(
    readVersion("/somewhere/qluent", {
      spawn: () => ({ status: 1, stdout: "", stderr: "boom" }),
    }),
    null
  );
  assert.equal(
    readVersion("/somewhere/qluent", {
      spawn: () => {
        throw new Error("spawn failed");
      },
    }),
    null
  );
});

test("detectVersionManager recognises version-scoped install prefixes", () => {
  assert.equal(
    detectVersionManager("/home/u/.local/share/fnm/node-versions/v22.23.1/bin"),
    "fnm"
  );
  assert.equal(detectVersionManager("/home/u/.nvm/versions/node/v20.0.0/bin"), "nvm");
  assert.equal(detectVersionManager("C:\\Users\\u\\AppData\\volta\\bin"), "volta");
  assert.equal(detectVersionManager("/usr/local/bin"), null);
  assert.equal(detectVersionManager(null), null);
});

test("formatShadowWarning names both paths, both versions and hash -r", () => {
  const warning = formatShadowWarning({
    shadowingPath: "/home/u/.local/bin/qluent",
    shadowingVersion: "0.1.15",
    installedPath: "/npm/node_modules/@qluent/cli/bin/qluent",
    installedVersion: "0.1.18",
    versionManager: null,
  });

  assert.match(warning, /\/home\/u\/\.local\/bin\/qluent/);
  assert.match(warning, /version 0\.1\.15/);
  assert.match(warning, /@qluent\/cli\/bin\/qluent/);
  assert.match(warning, /version 0\.1\.18/);
  assert.match(warning, /hash -r/);
  assert.doesNotMatch(warning, /node version/);
});

test("formatShadowWarning adds the version-manager caveat when relevant", () => {
  const warning = formatShadowWarning({
    shadowingPath: "/home/u/.local/bin/qluent",
    shadowingVersion: null,
    installedPath: "/fnm/bin/qluent",
    installedVersion: "0.1.18",
    versionManager: "fnm",
  });

  assert.match(warning, /fnm/);
  assert.match(warning, /active node version/);
  // An unknown version is simply omitted rather than printed as "undefined".
  assert.doesNotMatch(warning, /undefined/);
});

// ---------------------------------------------------------------------------
// warnIfShadowed
// ---------------------------------------------------------------------------

test("warnIfShadowed warns when an older qluent wins on PATH", () => {
  const root = makeTempDir();
  const other = path.join(root, "local-bin");
  const npmBin = path.join(root, "npm-bin");
  fs.mkdirSync(npmBin, { recursive: true });
  const shadowing = makeFakeBinary(other);
  const logger = collectingLogger();

  const warning = warnIfShadowed({
    installedPath: path.join(npmBin, "qluent"),
    installedVersion: "0.1.18",
    env: { PATH: [other, npmBin].join(path.delimiter), npm_config_prefix: root },
    platform: "linux",
    binDir: npmBin,
    packageDir: makeTempDir(),
    logger,
    spawn: () => ({ status: 0, stdout: "qluent, version 0.1.15\n", stderr: "" }),
  });

  assert.ok(warning);
  assert.equal(logger.messages.length, 1);
  assert.match(warning, new RegExp(shadowing.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(warning, /0\.1\.15/);
  assert.match(warning, /0\.1\.18/);
});

test("warnIfShadowed stays quiet when our bin directory wins", () => {
  const root = makeTempDir();
  const other = path.join(root, "local-bin");
  const npmBin = path.join(root, "npm-bin");
  fs.mkdirSync(npmBin, { recursive: true });
  makeFakeBinary(other);
  const logger = collectingLogger();

  const warning = warnIfShadowed({
    installedPath: path.join(npmBin, "qluent"),
    installedVersion: "0.1.18",
    env: { PATH: [npmBin, other].join(path.delimiter) },
    platform: "linux",
    binDir: npmBin,
    packageDir: makeTempDir(),
    logger,
    spawn: () => ({ status: 0, stdout: "qluent, version 0.1.15\n", stderr: "" }),
  });

  assert.equal(warning, null);
  assert.deepEqual(logger.messages, []);
});

test("warnIfShadowed stays quiet when the resolved entry is our own shim", () => {
  const root = makeTempDir();
  const packageDir = path.join(root, "node_modules", "@qluent", "cli");
  const shimDir = path.join(packageDir, "bin");
  makeFakeBinary(shimDir);
  const globalBin = path.join(root, "global-bin");
  fs.mkdirSync(globalBin, { recursive: true });
  fs.symlinkSync(path.join(shimDir, "qluent"), path.join(globalBin, "qluent"));
  const logger = collectingLogger();

  const warning = warnIfShadowed({
    installedPath: path.join(shimDir, "qluent"),
    installedVersion: "0.1.18",
    env: { PATH: globalBin },
    platform: "linux",
    binDir: shimDir,
    packageDir,
    logger,
    spawn: () => ({ status: 0, stdout: "qluent, version 0.1.18\n", stderr: "" }),
  });

  assert.equal(warning, null);
});

test("warnIfShadowed stays quiet when no qluent is on PATH", () => {
  const logger = collectingLogger();

  const warning = warnIfShadowed({
    installedPath: "/npm/bin/qluent",
    installedVersion: "0.1.18",
    env: { PATH: makeTempDir() },
    platform: "linux",
    binDir: makeTempDir(),
    packageDir: makeTempDir(),
    logger,
    spawn: () => ({ status: 0, stdout: "", stderr: "" }),
  });

  assert.equal(warning, null);
  assert.deepEqual(logger.messages, []);
});
