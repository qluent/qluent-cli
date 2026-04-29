from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from qluent_cli import plugin as plugin_module
from qluent_cli.auth import CallbackResult
from qluent_cli.main import cli


@pytest.fixture
def fake_browser_login(monkeypatch):
    def fake(api_url: str) -> CallbackResult:
        return CallbackResult(
            success=True,
            api_key="qk_plugin_test",
            project_uuid="proj-plugin",
            user_email="plugin@test.com",
        )

    monkeypatch.setattr("qluent_cli.auth.browser_login", fake)


def _completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout="", stderr=stderr
    )


def _completed_with_stdout(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_offer_install_skips_when_flag_false(monkeypatch):
    called = SimpleNamespace(value=False)
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: setattr(called, "value", True) or True,
    )

    plugin_module.offer_claude_plugin_install(False)

    assert called.value is False


def test_offer_install_runs_when_flag_true_and_plugin_missing(monkeypatch):
    calls = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: False)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: calls.append("ran") or True,
    )

    plugin_module.offer_claude_plugin_install(True)

    assert calls == ["ran"]


def test_offer_install_prints_hint_when_claude_missing(monkeypatch, capsys):
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: False)

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert "Claude Code CLI not detected" in err
    assert "claude plugin marketplace add" in err


def test_offer_install_prints_refresh_tip_when_already_installed(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: True)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: called.append("install") or True,
    )

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert called == []
    assert f"/plugin marketplace update {plugin_module.MARKETPLACE_NAME}" in err
    # No version comparison output should leak through.
    assert "up to date" not in err


def test_offer_install_does_not_print_freshness_verdict(monkeypatch, capsys):
    """Regression: the old `Claude Code plugin up to date: …` line is gone."""
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: True)

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert "Claude Code plugin up to date" not in err


def test_install_claude_plugin_runs_both_steps(monkeypatch):
    commands = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.install_claude_plugin() is True
    assert commands == [
        ["claude", "plugin", "marketplace", "add", plugin_module.MARKETPLACE_SOURCE],
        ["claude", "plugin", "install", plugin_module.PLUGIN_ID],
    ]


def test_install_claude_plugin_returns_false_on_step_failure(monkeypatch, capsys):
    def fake_run(cmd, **_kwargs):
        return _completed(returncode=1, stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.install_claude_plugin() is False
    err = capsys.readouterr().err
    assert "Failed: plugin marketplace add" in err
    assert "boom" in err


def test_install_claude_plugin_returns_false_on_timeout(monkeypatch, capsys):
    def fake_run(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=plugin_module._STEP_TIMEOUT_SECONDS)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.install_claude_plugin() is False
    err = capsys.readouterr().err
    assert "timed out" in err


def test_is_claude_plugin_installed_true_when_listed(monkeypatch):
    output = (
        "Installed plugins:\n"
        "\n"
        f"{plugin_module.PLUGIN_ID}\n"
        "Version: 0.3.0\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **_: _completed_with_stdout(output)
    )

    assert plugin_module.is_claude_plugin_installed() is True


def test_is_claude_plugin_installed_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **_: _completed_with_stdout("No plugins installed.\n"),
    )

    assert plugin_module.is_claude_plugin_installed() is False


def test_is_claude_plugin_installed_false_on_command_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: _completed(returncode=2))

    assert plugin_module.is_claude_plugin_installed() is False


def test_is_claude_plugin_installed_false_on_oserror(monkeypatch):
    def fake_run(cmd, **_):
        raise OSError("claude binary missing")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.is_claude_plugin_installed() is False


def test_login_install_plugin_flag_invokes_install(
    monkeypatch, isolated_config, fake_browser_login, tmp_path
):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: False)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: called.append("ran") or True,
    )

    result = CliRunner().invoke(cli, ["login", "--install-plugin"])

    assert result.exit_code == 0
    assert called == ["ran"]
    assert plugin_module.PLUGIN_ID in result.output


def test_login_no_install_plugin_skips(
    monkeypatch, isolated_config, fake_browser_login, tmp_path
):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: False)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: called.append("ran") or True,
    )

    result = CliRunner().invoke(cli, ["login", "--no-install-plugin"])

    assert result.exit_code == 0
    assert called == []


def test_login_prompt_declined(monkeypatch, isolated_config, fake_browser_login, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("existing content")
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: False)
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: called.append("ran") or True,
    )

    # First "n" declines AGENTS.md overwrite (we created one above),
    # second "n" declines plugin install.
    result = CliRunner().invoke(cli, ["login"], input="n\nn\n")

    assert result.exit_code == 0
    assert called == []


def test_login_emits_refresh_tip_when_plugin_already_installed(
    monkeypatch, isolated_config, fake_browser_login, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "is_claude_plugin_installed", lambda: True)

    result = CliRunner().invoke(cli, ["login"])

    assert result.exit_code == 0
    assert f"/plugin marketplace update {plugin_module.MARKETPLACE_NAME}" in result.output
    assert "Claude Code plugin up to date" not in result.output


def test_claude_update_subcommand_is_removed():
    """The freshness-check workaround command should no longer exist."""
    result = CliRunner().invoke(cli, ["claude", "update"])

    assert result.exit_code != 0
