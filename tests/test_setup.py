from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli import config as config_module
from qluent_cli.main import cli


def test_setup_saves_config_and_writes_claude_md(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup"],
        input=(
            "qk_test\n"
            "project-123\n"
            "user@example.com\n"
            "\n"
        ),
    )

    assert result.exit_code == 0
    saved = json.loads(config_file.read_text())
    assert saved == {
        "api_key": "qk_test",
        "api_url": config_module.DEFAULT_API_URL,
        "project_uuid": "project-123",
        "user_email": "user@example.com",
        "client_safe": True,
    }
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists()
    assert "# Qluent Metric Trees" in claude_md.read_text()


def test_setup_uses_production_default_api_url(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup"],
        input=(
            "qk_test\n"
            "project-123\n"
            "user@example.com\n"
            "n\n"
        ),
    )

    assert result.exit_code == 0
    saved = json.loads(config_file.read_text())
    assert saved["api_url"] == config_module.DEFAULT_API_URL


def test_setup_local_flag_prefills_local_api_url(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup", "--local"],
        input=(
            "qk_test\n"
            "project-123\n"
            "user@example.com\n"
            "n\n"
        ),
    )

    assert result.exit_code == 0
    saved = json.loads(config_file.read_text())
    assert saved["api_url"] == config_module.LOCAL_API_URL
    assert saved["client_safe"] is False
    assert "bearer_token" not in saved


def test_claude_init_writes_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["claude", "init"])

    assert result.exit_code == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert "# Qluent Metric Trees" in (tmp_path / "CLAUDE.md").read_text()


def test_claude_init_requires_force_to_overwrite(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("existing")

    result = CliRunner().invoke(cli, ["claude", "init"])

    assert result.exit_code != 0
    assert "already exists" in result.output
