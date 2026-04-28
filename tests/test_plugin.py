from __future__ import annotations

import subprocess
from types import SimpleNamespace

import click
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


def test_offer_install_runs_when_flag_true(monkeypatch):
    calls = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: None
    )
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


def test_login_install_plugin_flag_invokes_install(
    monkeypatch, isolated_config, fake_browser_login, tmp_path
):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: None
    )
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
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: None
    )
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
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: None
    )
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


def test_update_claude_plugin_runs_both_steps(monkeypatch):
    commands = []

    def fake_run(cmd, **_kwargs):
        commands.append(cmd)
        return _completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.update_claude_plugin() is True
    assert commands == [
        ["claude", "plugin", "marketplace", "update", plugin_module.MARKETPLACE_NAME],
        ["claude", "plugin", "update", plugin_module.PLUGIN_ID],
    ]


def test_update_claude_plugin_returns_false_on_step_failure(monkeypatch, capsys):
    def fake_run(cmd, **_kwargs):
        return _completed(returncode=1, stderr="network down")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.update_claude_plugin() is False
    err = capsys.readouterr().err
    assert "Failed: plugin marketplace update" in err
    assert "network down" in err


def test_claude_update_command_succeeds(monkeypatch):
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "update_claude_plugin", lambda: True)

    result = CliRunner().invoke(cli, ["claude", "update"])

    assert result.exit_code == 0
    assert plugin_module.PLUGIN_ID in result.output
    assert "up to date" in result.output


def test_claude_update_command_fails_when_claude_missing(monkeypatch):
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: False)

    result = CliRunner().invoke(cli, ["claude", "update"])

    assert result.exit_code != 0
    assert "Claude Code CLI not found" in result.output


def test_claude_update_command_fails_on_step_error(monkeypatch):
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(plugin_module, "update_claude_plugin", lambda: False)

    result = CliRunner().invoke(cli, ["claude", "update"])

    assert result.exit_code != 0
    assert "Plugin update failed" in result.output


# ---------------------------------------------------------------------------
# Version detection + stale-plugin prompt
# ---------------------------------------------------------------------------


def _completed_with_stdout(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_get_installed_version_parses_plugin_list(monkeypatch):
    output = (
        "Installed plugins:\n"
        "\n"
        f"{plugin_module.PLUGIN_ID}\n"
        "Version: 0.2.0\n"
        "\n"
        "other@thing\n"
        "Version: 9.9.9\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **_: _completed_with_stdout(output)
    )

    assert plugin_module.get_installed_claude_plugin_version() == "0.2.0"


def test_get_installed_version_returns_none_when_plugin_absent(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **_: _completed_with_stdout("No plugins installed.\n"),
    )

    assert plugin_module.get_installed_claude_plugin_version() is None


def test_get_installed_version_returns_none_on_command_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: _completed(returncode=2))

    assert plugin_module.get_installed_claude_plugin_version() is None


def test_get_installed_version_returns_none_on_oserror(monkeypatch):
    def fake_run(cmd, **_):
        raise OSError("claude binary missing")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert plugin_module.get_installed_claude_plugin_version() is None


def test_is_older_compares_dotted_versions():
    assert plugin_module._is_older("0.2.0", "0.3.0") is True
    assert plugin_module._is_older("0.3.0", "0.3.0") is False
    assert plugin_module._is_older("0.4.0", "0.3.0") is False
    assert plugin_module._is_older("0.2", "0.2.1") is True
    assert plugin_module._is_older("0.2.0-rc1", "0.3.0") is True


def test_is_older_handles_unparseable_versions():
    assert plugin_module._is_older("garbage", "0.3.0") is False


def test_offer_install_skips_install_when_plugin_already_current(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module,
        "get_installed_claude_plugin_version",
        lambda: plugin_module.RECOMMENDED_CLAUDE_PLUGIN_VERSION,
    )
    monkeypatch.setattr(
        plugin_module,
        "install_claude_plugin",
        lambda: called.append("install") or True,
    )
    monkeypatch.setattr(
        plugin_module,
        "update_claude_plugin",
        lambda: called.append("update") or True,
    )

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert called == []
    assert "up to date" in err
    assert plugin_module.RECOMMENDED_CLAUDE_PLUGIN_VERSION in err


def test_offer_install_prompts_to_update_when_stale_and_runs(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: "0.2.0"
    )
    monkeypatch.setattr(
        plugin_module, "RECOMMENDED_CLAUDE_PLUGIN_VERSION", "0.3.0"
    )
    monkeypatch.setattr(
        plugin_module, "update_claude_plugin", lambda: called.append("update") or True
    )
    monkeypatch.setattr(click, "confirm", lambda *a, **k: True)

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert called == ["update"]
    assert "update available" in err
    assert "0.2.0" in err
    assert "0.3.0" in err
    assert "updated to 0.3.0" in err


def test_offer_install_declined_update_prints_manual_command(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: "0.2.0"
    )
    monkeypatch.setattr(
        plugin_module, "RECOMMENDED_CLAUDE_PLUGIN_VERSION", "0.3.0"
    )
    monkeypatch.setattr(
        plugin_module, "update_claude_plugin", lambda: called.append("update") or True
    )
    monkeypatch.setattr(click, "confirm", lambda *a, **k: False)

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert called == []
    assert "qluent claude update" in err


def test_offer_install_stale_with_install_flag_true_skips_prompt(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: "0.2.0"
    )
    monkeypatch.setattr(
        plugin_module, "RECOMMENDED_CLAUDE_PLUGIN_VERSION", "0.3.0"
    )
    monkeypatch.setattr(
        plugin_module, "update_claude_plugin", lambda: called.append("update") or True
    )

    def fail_confirm(*_a, **_k):
        raise AssertionError("click.confirm should not be called when assume_yes is True")

    monkeypatch.setattr(click, "confirm", fail_confirm)

    plugin_module.offer_claude_plugin_install(True)

    assert called == ["update"]
    assert "updated to 0.3.0" in capsys.readouterr().err


def test_offer_install_stale_update_failure_reports_retry(monkeypatch, capsys):
    monkeypatch.setattr(plugin_module, "claude_cli_available", lambda: True)
    monkeypatch.setattr(
        plugin_module, "get_installed_claude_plugin_version", lambda: "0.2.0"
    )
    monkeypatch.setattr(
        plugin_module, "RECOMMENDED_CLAUDE_PLUGIN_VERSION", "0.3.0"
    )
    monkeypatch.setattr(plugin_module, "update_claude_plugin", lambda: False)
    monkeypatch.setattr(click, "confirm", lambda *a, **k: True)

    plugin_module.offer_claude_plugin_install(None)

    err = capsys.readouterr().err
    assert "Plugin update failed" in err
    assert "qluent claude update" in err
