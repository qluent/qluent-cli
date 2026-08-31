const assert = require("node:assert");
const test = require("node:test");
const path = require("node:path");

const pkg = require("../package.json");

// npm's provenance verification compares package.json's repository.url against
// the repository the OIDC token was issued for, and rejects the publish with a
// 422 when they disagree. An absent field reads as "" and fails the same way —
// after the binaries are built, signed and released, so the cost of finding out
// at publish time is a whole wasted release run.
const EXPECTED_REPOSITORY_URL = "git+https://github.com/qluent/qluent-cli.git";

test("package.json declares a repository for provenance verification", () => {
  assert.ok(pkg.repository, "package.json must declare a repository");
  assert.strictEqual(pkg.repository.type, "git");
  assert.strictEqual(pkg.repository.url, EXPECTED_REPOSITORY_URL);
});

test("repository.directory points at this package inside the monorepo", () => {
  assert.strictEqual(pkg.repository.directory, "npm");
});

test("every published file is present on disk", () => {
  const fs = require("node:fs");
  const root = path.join(__dirname, "..");
  for (const relative of pkg.files) {
    assert.ok(
      fs.existsSync(path.join(root, relative)),
      `package.json "files" lists ${relative}, which does not exist`
    );
  }
});

test("the postinstall entry point is published", () => {
  // install.js runs on every consumer install; shipping a package without it
  // would silently install no binary at all.
  assert.ok(pkg.files.includes("install.js"));
  assert.strictEqual(pkg.scripts.postinstall, "node install.js");
});
