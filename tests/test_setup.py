from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli import __version__
from qluent_cli import config as config_module
from qluent_cli.main import cli


def test_version_outputs_package_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert f"qluent, version {__version__}" in result.output


def test_setup_saves_config_and_writes_agents_md(monkeypatch, isolated_config, tmp_path):
    _config_dir, config_file = isolated_config
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup", "--no-install-plugin"],
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
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    assert "# Qluent" in agents_md.read_text()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_setup_uses_production_default_api_url(monkeypatch, isolated_config, tmp_path):
    _config_dir, config_file = isolated_config
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup", "--no-install-plugin"],
        input=(
            "qk_test\n"
            "project-123\n"
            "user@example.com\n"
            "n\n"
        ),
    )

    assert result.exit_code == 0
    assert "Skipped AGENTS.md generation" in result.output
    saved = json.loads(config_file.read_text())
    assert saved["api_url"] == config_module.DEFAULT_API_URL


def test_setup_local_flag_prefills_local_api_url(monkeypatch, isolated_config, tmp_path):
    _config_dir, config_file = isolated_config
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["setup", "--local", "--no-install-plugin"],
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
    assert "# Qluent" in (tmp_path / "CLAUDE.md").read_text()


def test_claude_init_requires_force_to_overwrite(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("existing")

    result = CliRunner().invoke(cli, ["claude", "init"])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_agents_init_default_writes_agents_md(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["agents", "init"])

    assert result.exit_code == 0
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    assert "# Qluent" in agents_md.read_text()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_agents_init_as_claude_writes_claude_md(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["agents", "init", "--as", "claude"])

    assert result.exit_code == 0
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists()
    assert "# Qluent" in claude_md.read_text()
    assert not (tmp_path / "AGENTS.md").exists()


def test_agents_init_as_both_writes_agents_and_claude_pointer(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["agents", "init", "--as", "both"])

    assert result.exit_code == 0
    agents_md = tmp_path / "AGENTS.md"
    claude_md = tmp_path / "CLAUDE.md"
    assert agents_md.exists()
    assert claude_md.exists()
    # AGENTS.md gets the full instructions; CLAUDE.md imports it for Claude Code.
    assert "Shapley" in agents_md.read_text()
    pointer = claude_md.read_text()
    assert pointer.startswith("@AGENTS.md\n")
    assert "Shapley" not in pointer


def test_agents_init_requires_force_to_overwrite(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("existing")

    result = CliRunner().invoke(cli, ["agents", "init"])

    assert result.exit_code != 0
    assert "already exists" in result.output

    forced = CliRunner().invoke(cli, ["agents", "init", "--force"])
    assert forced.exit_code == 0
    assert "# Qluent" in (tmp_path / "AGENTS.md").read_text()


def test_agents_init_as_both_rejects_custom_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli, ["agents", "init", "--as", "both", "--path", "elsewhere.md"]
    )

    assert result.exit_code != 0
    assert "incompatible" in result.output


def test_setup_accepts_deprecated_claude_path_alias(
    monkeypatch, isolated_config, tmp_path
):
    _config_dir, _config_file = isolated_config
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "setup",
            "--no-install-plugin",
            "--claude-path",
            "CUSTOM_CLAUDE.md",
        ],
        input=(
            "qk_test\n"
            "project-123\n"
            "user@example.com\n"
            "\n"
        ),
    )

    assert result.exit_code == 0
    custom_path = tmp_path / "CUSTOM_CLAUDE.md"
    assert custom_path.exists()
    assert "# Qluent" in custom_path.read_text()
    assert not (tmp_path / "AGENTS.md").exists()


def test_status_outputs_connected_project_and_trees(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.main.load_config",
        lambda: config_module.QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
        ),
    )

    def mock_list_trees(self):
        return {
            "trees": [
                {
                    "id": "revenue",
                    "label": "Revenue",
                    "nodes": [
                        {"id": "net_revenue", "label": "Net Revenue", "kind": "sql_metric"},
                        {"id": "orders", "label": "Orders", "kind": "sql_metric"},
                    ],
                }
            ]
        }

    monkeypatch.setattr("qluent_cli.main.QluentClient.list_trees", mock_list_trees)

    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0
    assert "Connected to Qluent" in result.output
    assert "UUID: project-123" in result.output
    assert "API: https://api.example.com" in result.output
    assert "User: user@example.com" in result.output
    assert "revenue" in result.output
    assert "Net Revenue, Orders" in result.output
    assert "Query             ready (default)" in result.output
    assert "Metric trees      1 available (advanced)" in result.output
    assert "qluent suggestions --json-output" in result.output


def test_whoami_json_outputs_agent_friendly_status(monkeypatch):
    monkeypatch.setattr(
        "qluent_cli.main.load_config",
        lambda: config_module.QluentConfig(
            api_key="qk_test",
            api_url="https://api.example.com",
            project_uuid="project-123",
            user_email="user@example.com",
            client_safe=True,
        ),
    )
    monkeypatch.setattr("qluent_cli.main.QluentClient.list_trees", lambda self: {"trees": []})

    result = CliRunner().invoke(cli, ["whoami", "--json-output"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["connected"] is True
    assert payload["project"] == {
        "uuid": "project-123",
        "api_url": "https://api.example.com",
        "user_email": "user@example.com",
        "client_safe": True,
    }
    assert payload["trees"] == []
    assert payload["capabilities"] == {
        "query": {
            "available": True,
            "status": "ready",
            "default": True,
        },
        "metric_trees": {
            "available": False,
            "status": "not_configured",
            "count": 0,
            "advanced": True,
        },
    }
    assert payload["suggested_first_command"] == "qluent suggestions --json-output"


def test_status_explains_login_when_not_configured(monkeypatch):
    def missing_config():
        raise SystemExit("No API key configured. Run: qluent login")

    monkeypatch.setattr("qluent_cli.main.load_config", missing_config)

    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0
    assert "Not connected to Qluent" in result.output
    assert "Run: qluent login" in result.output
