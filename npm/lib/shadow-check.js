// Post-install sanity check: does `qluent` on the user's PATH actually resolve
// to the binary we just installed?
//
// `npm install -g @qluent/cli` can report success while an older `qluent`
// (a uv tool install, a distro package) keeps winning on PATH, so the user
// believes they upgraded and stays on the old CLI. Two things make it common:
// shells cache resolved paths (`hash -r` / `rehash` clears that), and node
// version managers put npm's global bin under the *active node version*, so
// the install effectively disappears when that environment is not present.
//
// This only ever warns — never fail an install over it.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const PACKAGE_DIR = path.join(__dirname, "..");

// Directory names that mean npm's global bin is scoped to a node version.
const VERSION_MANAGER_MARKERS = ["fnm", "nvm", "volta", "nodenv", "asdf", "nvs"];

function pathEntries({ env = process.env, platform = process.platform } = {}) {
  const raw = env.PATH || env.Path || env.path || "";
  const delimiter = platform === "win32" ? ";" : ":";
  return raw
    .split(delimiter)
    .map((entry) => entry.trim().replace(/^"(.*)"$/, "$1"))
    .filter(Boolean);
}

/** Filenames a shell would try for `name` in a PATH directory. */
function executableNames(name, { env = process.env, platform = process.platform } = {}) {
  if (platform !== "win32") {
    return [name];
  }
  const extensions = (env.PATHEXT || ".COM;.EXE;.BAT;.CMD")
    .split(";")
    .map((ext) => ext.trim())
    .filter(Boolean);
  return extensions.map((ext) => `${name}${ext.toLowerCase()}`).concat(name);
}

function isExecutableFile(candidate, { platform = process.platform } = {}) {
  try {
    if (!fs.statSync(candidate).isFile()) {
      return false;
    }
  } catch {
    return false;
  }
  if (platform === "win32") {
    return true;
  }
  try {
    fs.accessSync(candidate, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function realPath(target) {
  try {
    return fs.realpathSync(target);
  } catch {
    return path.resolve(target);
  }
}

function sameDirectory(a, b) {
  if (!a || !b) {
    return false;
  }
  return realPath(a) === realPath(b);
}

/**
 * Where npm links global bins. During `postinstall` the link may not exist
 * yet, so we compare PATH *positions* rather than looking for the file.
 */
function npmBinDirs({
  env = process.env,
  platform = process.platform,
  binDir,
} = {}) {
  const dirs = [];
  const prefix = env.npm_config_prefix;
  if (prefix) {
    dirs.push(platform === "win32" ? prefix : path.join(prefix, "bin"));
  }
  if (process.execPath) {
    dirs.push(path.dirname(process.execPath));
  }
  if (binDir) {
    dirs.push(binDir);
  }
  return dirs;
}

/**
 * Walk PATH in order and stop at the first entry that either is one of our own
 * bin directories or holds an executable named `name`.
 *
 * Returns `{ kind: "ours" | "foreign" | "none", directory, resolved }`. A PATH
 * entry of ours that comes first wins even when it is still empty: npm creates
 * the link after this script runs, and it will then shadow anything later.
 */
function resolveFirstOnPath(
  name,
  { env = process.env, platform = process.platform, ownDirs = [] } = {}
) {
  const candidateNames = executableNames(name, { env, platform });

  for (const directory of pathEntries({ env, platform })) {
    if (ownDirs.some((own) => sameDirectory(own, directory))) {
      return { kind: "ours", directory, resolved: null };
    }
    for (const candidateName of candidateNames) {
      const candidate = path.join(directory, candidateName);
      if (isExecutableFile(candidate, { platform })) {
        return { kind: "foreign", directory, resolved: candidate };
      }
    }
  }

  return { kind: "none", directory: null, resolved: null };
}

/** True when the resolved entry is this package's shim after all. */
function belongsToThisPackage(resolved, { packageDir = PACKAGE_DIR } = {}) {
  if (!resolved) {
    return false;
  }
  const real = realPath(resolved);
  const root = realPath(packageDir);
  if (real === root || real.startsWith(root + path.sep)) {
    return true;
  }
  // npm's Windows wrappers (.cmd/.ps1) are generated files, not symlinks, so
  // path comparison misses them — look for the package they point at.
  try {
    if (fs.statSync(real).size > 8 * 1024) {
      return false;
    }
    return fs.readFileSync(real, "utf8").includes("@qluent/cli");
  } catch {
    return false;
  }
}

/** Ask an executable for its version. Returns null if it cannot be run. */
function readVersion(executable, { spawn = spawnSync } = {}) {
  try {
    const result = spawn(executable, ["--version"], {
      encoding: "utf8",
      timeout: 10_000,
      windowsHide: true,
    });
    if (!result || result.error || result.status !== 0) {
      return null;
    }
    const output = `${result.stdout || ""} ${result.stderr || ""}`;
    const match = output.match(/\d+\.\d+\.\d+\S*/);
    return match ? match[0] : null;
  } catch {
    return null;
  }
}

/** Name the node version manager whose directory layout contains `target`. */
function detectVersionManager(target) {
  if (!target) {
    return null;
  }
  const segments = target.split(/[\\/]/).map((segment) => segment.toLowerCase());
  for (const marker of VERSION_MANAGER_MARKERS) {
    if (segments.some((segment) => segment === marker || segment === `.${marker}`)) {
      return marker;
    }
  }
  if (segments.includes("node-versions")) {
    return "a node version manager";
  }
  return null;
}

function formatShadowWarning({
  shadowingPath,
  shadowingVersion,
  installedPath,
  installedVersion,
  versionManager,
}) {
  const describe = (version) => (version ? ` (version ${version})` : "");
  const lines = [
    "WARNING: `qluent` on your PATH is not the CLI that was just installed.",
    `  PATH resolves to: ${shadowingPath}${describe(shadowingVersion)}`,
    `  just installed:   ${installedPath}${describe(installedVersion)}`,
    "",
    "Until that is fixed, `qluent` keeps running the other install. Either",
    "remove/upgrade it, or put npm's global bin directory earlier on PATH.",
    "If you already ran `qluent` in this shell, clear its cached lookup with",
    "`hash -r` (bash) or `rehash` (zsh).",
  ];
  if (versionManager) {
    lines.push(
      "",
      `Note: npm's global bin lives under ${versionManager}, so it is scoped to`,
      "the active node version — the CLI disappears from PATH after a node",
      "upgrade or in shells started without that environment."
    );
  }
  return lines.join("\n");
}

/**
 * Warn when another `qluent` wins on PATH. Returns the warning text (also
 * logged), or null when the install is the one that will be used.
 */
function warnIfShadowed({
  installedPath,
  installedVersion,
  env = process.env,
  platform = process.platform,
  binDir = path.join(PACKAGE_DIR, "bin"),
  packageDir = PACKAGE_DIR,
  logger = console,
  spawn = spawnSync,
} = {}) {
  const ownDirs = npmBinDirs({ env, platform, binDir });
  const found = resolveFirstOnPath("qluent", { env, platform, ownDirs });

  if (found.kind !== "foreign") {
    return null;
  }
  if (belongsToThisPackage(found.resolved, { packageDir })) {
    return null;
  }

  const warning = formatShadowWarning({
    shadowingPath: found.resolved,
    shadowingVersion: readVersion(found.resolved, { spawn }),
    installedPath,
    installedVersion,
    versionManager: detectVersionManager(ownDirs[0] || binDir),
  });
  logger.warn ? logger.warn(warning) : logger.log(warning);
  return warning;
}

module.exports = {
  PACKAGE_DIR,
  VERSION_MANAGER_MARKERS,
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
};
