# Splitting `qluent-cli` Into Its Own Repository

This guide assumes the current source lives under `cli/` in the monorepo and you want a
standalone `qluent-cli` repository with preserved history.

## Goal

After the split, the new repository should contain:

- the Python CLI package under `src/qluent_cli/`
- the npm wrapper under `npm/`
- the standalone release workflow under `.github/workflows/`
- the smoke-test script under `scripts/`

The backend and workflow engine stay in the main product repo. Only the CLI distribution surface
moves.

## Recommended approach

Use `git subtree split` so the new repository keeps the CLI history:

```bash
git subtree split --prefix=cli -b codex/qluent-cli-split
```

Then create the new repository and push that branch into it:

```bash
git remote add qluent-cli git@github.com:<org>/qluent-cli.git
git push qluent-cli codex/qluent-cli-split:main
```

## Before pushing

Verify that the split branch contains these paths at repository root:

```text
.github/workflows/qluent-cli-binaries.yml
README.md
REPO_SPLIT.md
pyproject.toml
src/qluent_cli/
npm/
scripts/
tests/
```

## After the split

Run the normal source checks from the new repo root:

```bash
uv sync
uv run pytest
uv run --extra build python -m qluent_cli.build_binary
```

Then verify the npm wrapper locally:

```bash
QLUENT_SMOKE_NPM=1 scripts/local_smoke_test.sh
```

## Cleanup in the monorepo

Once the new repo is live, decide whether the monorepo should:

- keep a copy of `cli/` temporarily while migration happens, or
- remove `cli/` and treat the CLI as an external released artifact

If the CLI moves fully out of the monorepo, update any docs or internal setup instructions that
still point at `cli/` paths.
