from __future__ import annotations

import json

from click.testing import CliRunner

from qluent_cli import config as config_module
from qluent_cli.auth import CallbackResult
from qluent_cli.main import cli


def _mock_browser_login(result: CallbackResult):
    """Return a function that ignores api_url and returns the given result."""
    def fake_browser_login(api_url: str) -> CallbackResult:
        fake_browser_login.called_with_url = api_url  # type: ignore[attr-defined]
        return result
    return fake_browser_login


def test_login_saves_config_on_success(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    monkeypatch.setattr(
        "qluent_cli.auth.browser_login",
        _mock_browser_login(
            CallbackResult(
                success=True,
                api_key="qk_login_test",
                project_uuid="proj-login",
                user_email="login@test.com",
            )
        ),
    )

    result = CliRunner().invoke(cli, ["login"])

    assert result.exit_code == 0
    assert "Logged in successfully" in result.output
    assert "proj-login" in result.output
    assert "login@test.com" in result.output

    saved = json.loads(config_file.read_text())
    assert saved["api_key"] == "qk_login_test"
    assert saved["project_uuid"] == "proj-login"
    assert saved["user_email"] == "login@test.com"
    assert saved["api_url"] == config_module.DEFAULT_API_URL


def test_login_shows_error_on_failure(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    monkeypatch.setattr(
        "qluent_cli.auth.browser_login",
        _mock_browser_login(
            CallbackResult(success=False, error="Timed out")
        ),
    )

    result = CliRunner().invoke(cli, ["login"])

    assert result.exit_code != 0
    assert "Login failed" in result.output
    assert "Timed out" in result.output


def test_login_local_flag_uses_local_url(monkeypatch, tmp_path):
    config_dir = tmp_path / ".qluent"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    fake = _mock_browser_login(
        CallbackResult(
            success=True,
            api_key="qk_local",
            project_uuid="proj-local",
            user_email="local@test.com",
        )
    )
    monkeypatch.setattr("qluent_cli.auth.browser_login", fake)

    result = CliRunner().invoke(cli, ["login", "--local"])

    assert result.exit_code == 0
    assert fake.called_with_url == config_module.LOCAL_API_URL  # type: ignore[attr-defined]

    saved = json.loads(config_file.read_text())
    assert saved["api_url"] == config_module.LOCAL_API_URL
    assert saved["client_safe"] is False
