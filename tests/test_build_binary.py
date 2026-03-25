from __future__ import annotations

import pytest

from qluent_cli.build_binary import (
    artifact_name,
    executable_name,
    normalize_arch,
    normalize_platform,
)


def test_normalize_platform():
    assert normalize_platform("darwin") == "darwin"
    assert normalize_platform("linux") == "linux"
    assert normalize_platform("win32") == "windows"


def test_normalize_arch():
    assert normalize_arch("arm64") == "arm64"
    assert normalize_arch("aarch64") == "arm64"
    assert normalize_arch("x86_64") == "x64"
    assert normalize_arch("amd64") == "x64"


def test_artifact_name_matches_npm_convention():
    assert artifact_name("darwin", "arm64") == "qluent-darwin-arm64"
    assert artifact_name("linux", "x64") == "qluent-linux-x64"
    assert artifact_name("windows", "x64") == "qluent-windows-x64.exe"
    assert executable_name("windows") == "qluent.exe"
    assert executable_name("darwin") == "qluent"


def test_unsupported_platform_and_arch_raise():
    with pytest.raises(ValueError):
        normalize_platform("solaris")
    with pytest.raises(ValueError):
        normalize_arch("ppc64")
