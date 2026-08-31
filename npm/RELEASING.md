# Releasing `@qluent/cli`

This package is a thin npm installer for the platform-specific `qluent` binary.

## Overview

Releasing is one command from a clean `main`:

```bash
make bump VERSION=0.1.21     # rewrites all four manifests
git commit -am "Release 0.1.21"
# open a PR, merge it, pull main, then:
make release VERSION=0.1.21  # verifies, tests, tags, pushes
```

Pushing the `v*` tag triggers
[.github/workflows/qluent-cli-binaries.yml](../.github/workflows/qluent-cli-binaries.yml),
which runs three jobs in order:

1. **build** — one native binary per target on its own runner.
2. **release** — verifies the tag matches the committed version, verifies all
   five platform artifacts are present, signs the checksums, and publishes the
   GitHub Release.
3. **npm-publish** — re-verifies the tag against `package.json`, runs the
   installer tests, and publishes `@qluent/cli` over OIDC trusted publishing,
   which attaches provenance automatically.

`npm-publish` `needs: release`, which is the point: the package can never be
published pointing at a GitHub Release that does not exist yet.

## Version manifests

The version lives in four files. Never edit them by hand:

```text
pyproject.toml               project.version
src/qluent_cli/__init__.py   __version__
npm/package.json             version
uv.lock                      the qluent-cli package entry
```

`scripts/bump_version.py` writes all four; `--check` verifies they agree and is
enforced on every PR by [CI](../.github/workflows/ci.yml) and again at tag time.

## Build targets

`lib/installer.js` resolves five artifacts, so the build matrix must produce
five. Any target missing from the matrix 404s at `npm install` time on that
platform and nowhere else:

| Artifact | Runner |
| --- | --- |
| `qluent-darwin-arm64` | `macos-14` |
| `qluent-darwin-x64` | `macos-15-intel` |
| `qluent-linux-x64` | `ubuntu-latest` |
| `qluent-linux-arm64` | `ubuntu-24.04-arm` |
| `qluent-windows-x64.exe` | `windows-latest` |

The release job hard-fails on a missing artifact rather than publishing a
partial release.

Action versions are load-bearing too. Most actions publish a floating major
tag (`@v7`), but not all do — `astral-sh/setup-uv` stopped after `v7`, so it is
pinned to an exact version. A tag that does not resolve fails the job outright,
which is at least loud.

Runner labels are load-bearing and they expire. A label that no longer exists
does not fail the build — it queues until GitHub gives up, which is how the
retired `macos-13` image silently stalled the first 0.1.19 attempt. The build
job carries a 30-minute timeout so that shows up as a failure. GitHub drops
x86_64 macOS entirely when the macOS 15 image retires in Fall 2027; after that,
`qluent-darwin-x64` needs cross-compilation under Rosetta on an arm64 runner.

Final URLs, for `v0.1.21`:

```text
https://github.com/qluent/qluent-cli/releases/download/v0.1.21/qluent-darwin-arm64
https://github.com/qluent/qluent-cli/releases/download/v0.1.21/qluent-darwin-arm64.sha256
https://github.com/qluent/qluent-cli/releases/download/v0.1.21/qluent-darwin-arm64.sha256.sig
```

The npm installer verifies each downloaded binary against its checksum sidecar
and its Ed25519 signature before installing.

## Authentication

### npm: trusted publishing, not a token

`npm-publish` authenticates over OIDC. There is no npm token in this repo, and
there is nothing to rotate or leak. npmjs.com is configured to trust exactly one
workflow in one repository, so a stolen GitHub secret cannot publish `@qluent/cli`
from anywhere else.

Two consequences to keep in mind:

- **The workflow filename is load-bearing.** The trusted publisher is registered
  against `qluent-cli-binaries.yml`. Renaming that file breaks publishing until
  the setting on npmjs.com is updated to match.
- **npm must be >= 11.5.1 and Node >= 22.14.0.** Node 22 still bundles npm 10,
  so the job upgrades npm explicitly before publishing.

Provenance attestations are generated automatically under trusted publishing;
the `--provenance` flag is not needed and is deliberately absent.

Provenance also imposes a requirement on the manifest: `repository.url` in
`npm/package.json` must match the repository the OIDC token was issued for, or
the registry rejects the upload with a 422 after the binaries have already been
built, signed and released. `npm/tests/package-manifest.test.js` pins that
field so the failure surfaces on a PR rather than mid-release.

To reconfigure it: npmjs.com → the `@qluent/cli` package → Settings → Trusted
Publisher → GitHub Actions.

| Field | Value |
| --- | --- |
| Publisher | GitHub Actions |
| Organization or user | `qluent` |
| Repository | `qluent-cli` |
| Workflow filename | `qluent-cli-binaries.yml` |
| Environment name | *(empty)* |
| Allowed actions | **Allow `npm publish`** only |

Leave `Allow npm stage publish` unchecked: the workflow runs a plain
`npm publish`, and granting only what it actually does is the same reasoning
that made trusted publishing preferable to a token.

Only GitHub-hosted runners are supported, and a package can have one trusted
publisher at a time.

### GitHub Actions secrets

| Secret | Used by | Purpose |
| --- | --- | --- |
| `QLUENT_SIGNING_PRIVATE_KEY` | `release` | Ed25519 PEM key that signs the checksum sidecars |

That is the only secret this repo needs.

## Releasing the plugin

The Claude Code plugin lives in
[qluent-plugin-cc](https://github.com/qluent/qluent-plugin-cc) and depends on
this CLI, never the reverse. `QLUENT_MIN_CLI_VERSION` in
`plugins/qluent/scripts/cli-requirements.sh` is the declared contract between
them.

**Always release the CLI first.** A CLI release is backward-compatible for
plugin users; a plugin release that raised its minimum is not, and it points
users at an upgrade that does not exist yet. Plugin CI enforces this by
checking `QLUENT_MIN_CLI_VERSION` against the latest version published here.

## Manual fallback

If you need to build locally rather than in CI:

```bash
make binary   # current platform only — PyInstaller does not cross-compile
make smoke    # build plus an end-to-end smoke test
```

Then verify a published release before announcing it:

```bash
npm install -g @qluent/cli
qluent --version
```

## Signing key management

Release binaries are signed with Ed25519. The private key is stored as the
GitHub Actions secret `QLUENT_SIGNING_PRIVATE_KEY` (PEM format). The public key
is embedded in `lib/installer.js` in the `TRUSTED_PUBLIC_KEYS` array.

### Initial setup

Generate a keypair (one-time):

```bash
node -e "
const crypto = require('crypto');
const kp = crypto.generateKeyPairSync('ed25519');
console.log(kp.privateKey.export({ type: 'pkcs8', format: 'pem' }));
console.log('Public key (raw hex):',
  kp.publicKey.export({ type: 'spki', format: 'der' }).slice(12).toString('hex'));
"
```

1. Store the PEM private key as `QLUENT_SIGNING_PRIVATE_KEY` in GitHub Actions secrets.
2. Replace the placeholder in `TRUSTED_PUBLIC_KEYS` in `lib/installer.js` with the hex public key.

### Key rotation

1. Generate a new keypair.
2. **Prepend** the new public key to `TRUSTED_PUBLIC_KEYS` in `lib/installer.js`.
3. Publish the npm package (now trusts both old and new keys).
4. Update the `QLUENT_SIGNING_PRIVATE_KEY` secret to the new private key.
5. After a grace period (2-3 releases), remove the old public key from the array.

### Signature verification

`SIGNATURE_REQUIRED = true` in `lib/installer.js`: every release must carry
`.sha256.sig` sidecars or installs fail. `QLUENT_CLI_SKIP_SIGNATURE_VERIFICATION=1`
remains the escape hatch. The release job fails when
`QLUENT_SIGNING_PRIVATE_KEY` is unset, so an unsigned release cannot ship.

## Rollback

The workflow's job ordering makes the classic failure — npm published against a
missing release — unreachable. What remains:

**npm publish failed, GitHub Release succeeded.** The tag and release are fine;
nothing points at them yet. Fix the cause and re-run the `npm-publish` job from
the Actions UI. No version bump needed.

**Both succeeded but the build is bad.** Do not unpublish; `npm deprecate` the
version and roll forward with a patch release:

```bash
npm deprecate @qluent/cli@0.1.21 "Broken build, use 0.1.22"
```

The npm package version and the release tag are always equal, verified twice in
the workflow. Keep it that way.
