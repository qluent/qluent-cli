"""Tests for scripts/bump_version.py.

A regex that silently stops matching would let the release workflow tag a
version that half the manifests disagree with, so the patterns are pinned here
against realistic file bodies.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bump_version"] = module
    spec.loader.exec_module(module)
    return module


bump_version = _load_module()


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A miniature repo whose four manifests all sit at 1.2.3."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "qluent-cli"\n'
        'version = "1.2.3"\n'
        'dependencies = [\n'
        '    "click>=8.0",\n'
        ']\n'
    )
    package = tmp_path / "src" / "qluent_cli"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Docstring."""\n\n__version__ = "1.2.3"\n')
    npm = tmp_path / "npm"
    npm.mkdir()
    (npm / "package.json").write_text(
        '{\n  "name": "@qluent/cli",\n  "version": "1.2.3",\n  "license": "UNLICENSED"\n}\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\n'
        'name = "click"\n'
        'version = "8.1.7"\n'
        '\n'
        '[[package]]\n'
        'name = "qluent-cli"\n'
        'version = "1.2.3"\n'
        'source = { editable = "." }\n'
    )
    return tmp_path


def test_every_target_is_found(fake_root: Path) -> None:
    for target in bump_version.targets(fake_root):
        assert target.read() == "1.2.3", target.label


def test_check_passes_when_manifests_agree(fake_root: Path, capsys) -> None:
    bump_version.check(fake_root, None)
    assert "1.2.3" in capsys.readouterr().out


def test_check_accepts_a_matching_expected_version(fake_root: Path) -> None:
    bump_version.check(fake_root, "1.2.3")


def test_check_rejects_a_mismatched_expected_version(fake_root: Path) -> None:
    with pytest.raises(SystemExit):
        bump_version.check(fake_root, "1.2.4")


def test_check_detects_drift(fake_root: Path) -> None:
    path = fake_root / "npm" / "package.json"
    path.write_text(path.read_text().replace("1.2.3", "1.2.4"))
    with pytest.raises(SystemExit):
        bump_version.check(fake_root, None)


def test_bump_rewrites_every_manifest(fake_root: Path) -> None:
    bump_version.bump(fake_root, "1.3.0")
    bump_version.check(fake_root, "1.3.0")


def test_bump_leaves_other_packages_alone(fake_root: Path) -> None:
    """uv.lock lists many packages; only the qluent-cli entry may move."""
    bump_version.bump(fake_root, "1.3.0")
    lock = (fake_root / "uv.lock").read_text()
    assert 'name = "click"\nversion = "8.1.7"' in lock
    assert 'name = "qluent-cli"\nversion = "1.3.0"' in lock


def test_bump_leaves_dependency_pins_alone(fake_root: Path) -> None:
    bump_version.bump(fake_root, "1.3.0")
    assert '"click>=8.0"' in (fake_root / "pyproject.toml").read_text()


def test_bump_rejects_a_non_semver_version(fake_root: Path) -> None:
    with pytest.raises(SystemExit):
        bump_version.bump(fake_root, "not-a-version")


def test_bump_accepts_a_prerelease(fake_root: Path) -> None:
    bump_version.bump(fake_root, "1.3.0-rc1")
    bump_version.check(fake_root, "1.3.0-rc1")


def test_real_repo_manifests_are_in_sync() -> None:
    """The guard CI and the release workflow both run."""
    bump_version.check(REPO_ROOT, None)
