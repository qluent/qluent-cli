from __future__ import annotations

import sys
from pathlib import Path

import pytest

from qluent_cli import config as config_module


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def isolated_config(monkeypatch, tmp_path):
    """Redirect config to a temp directory and clear env vars."""
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    for var in (
        "QLUENT_API_KEY",
        "QLUENT_API_URL",
        "QLUENT_PROJECT_UUID",
        "QLUENT_USER_EMAIL",
        "QLUENT_CLIENT_SAFE",
        "QLUENT_BEARER_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    return config_dir, config_file
