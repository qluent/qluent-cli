#!/usr/bin/env python3
"""Single source of truth for the qluent-cli version.

The version is duplicated across four files that must never drift: a stale
``npm/package.json`` makes the installer download from a release URL that does
not exist, which only surfaces on a user's machine at ``npm install`` time.

Usage:
  python scripts/bump_version.py <version>          Bump every manifest.
  python scripts/bump_version.py --check [version]  Verify they agree.
                                                    Pass <version> to require
                                                    a specific value.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

ROOT = Path(__file__).resolve().parent.parent


class Target:
    """One version string in one file."""

    def __init__(self, label: str, path: Path, pattern: re.Pattern[str]) -> None:
        self.label = label
        self.path = path
        self.pattern = pattern

    def read(self) -> str | None:
        match = self.pattern.search(self.path.read_text())
        return match.group("version") if match else None

    def write(self, version: str) -> None:
        text = self.path.read_text()
        new_text, count = self.pattern.subn(
            lambda m: m.group(0).replace(m.group("version"), version, 1), text, count=1
        )
        if count != 1:
            die(f"Could not locate the version in {self.path}")
        self.path.write_text(new_text)


def targets(root: Path) -> list[Target]:
    return [
        Target(
            "pyproject.toml (project.version)",
            root / "pyproject.toml",
            # Anchored to a line-initial `version =`, which only the [project]
            # block has; dependency pins are all indented inside arrays.
            re.compile(r'(?m)^version = "(?P<version>[^"]+)"'),
        ),
        Target(
            "src/qluent_cli/__init__.py (__version__)",
            root / "src" / "qluent_cli" / "__init__.py",
            re.compile(r'(?m)^__version__ = "(?P<version>[^"]+)"'),
        ),
        Target(
            "npm/package.json (version)",
            root / "npm" / "package.json",
            re.compile(r'(?m)^  "version": "(?P<version>[^"]+)"'),
        ),
        Target(
            "uv.lock (qluent-cli package)",
            root / "uv.lock",
            # Only the self-entry; every other package has its own version line.
            re.compile(r'(?m)^name = "qluent-cli"\nversion = "(?P<version>[^"]+)"'),
        ),
    ]


def die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def check(root: Path, expected: str | None) -> None:
    found = [(t.label, t.read()) for t in targets(root)]
    distinct = {version for _, version in found}

    if len(distinct) != 1:
        print("Error: version drift detected across manifests:", file=sys.stderr)
        for label, version in found:
            print(f"  {label}: {version or '(missing)'}", file=sys.stderr)
        raise SystemExit(1)

    (actual,) = distinct
    if not actual or not SEMVER.match(actual):
        die(f'Version "{actual}" is not a valid semver string')
    if expected and actual != expected:
        die(f'Expected version "{expected}" but found "{actual}"')

    print(f"OK: every manifest is at {actual}")


def bump(root: Path, version: str) -> None:
    if not SEMVER.match(version):
        die(f'"{version}" is not a valid semver string')
    items = targets(root)
    for target in items:
        target.write(version)
    print(f"Bumped {len(items)} file(s) to {version}:")
    for target in items:
        print(f"  {target.path.relative_to(root)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump or verify the qluent-cli version across every manifest."
    )
    parser.add_argument(
        "version", nargs="?", help="the version to set, or to require with --check"
    )
    parser.add_argument("--check", action="store_true", help="verify instead of bumping")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args()

    if args.check:
        check(args.root, args.version)
    elif args.version:
        bump(args.root, args.version)
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
