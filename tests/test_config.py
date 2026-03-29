from __future__ import annotations

import json

import pytest

from qluent_cli import config as config_module


def test_default_client_safe_prefers_hosted_urls():
    assert config_module.default_client_safe("https://api.example.com") is True
    assert config_module.default_client_safe("http://localhost:8001") is False
    assert config_module.default_client_safe("http://127.0.0.1:8001") is False


def test_load_config_defaults_to_production_api_url(isolated_config):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "api_key": "qk_test",
                "project_uuid": "project-123",
                "user_email": "user@example.com",
            }
        )
    )

    loaded = config_module.load_config()

    assert loaded.api_url == config_module.DEFAULT_API_URL
    assert loaded.client_safe is True


def test_load_config_uses_client_safe_default_when_not_persisted(isolated_config):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "api_key": "qk_test",
                "api_url": "https://api.example.com",
                "project_uuid": "project-123",
                "user_email": "user@example.com",
            }
        )
    )

    loaded = config_module.load_config()

    assert loaded.client_safe is True


def test_load_config_rejects_http_non_local_url(isolated_config):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "api_key": "qk_test",
                "api_url": "http://api.example.com",
                "project_uuid": "project-123",
                "user_email": "user@example.com",
            }
        )
    )

    with pytest.raises(SystemExit, match="Refusing to connect over plain HTTP"):
        config_module.load_config()


def test_load_config_rejects_bearer_token_without_api_key(isolated_config):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "bearer_token": "jwt_token_here",
                "api_url": "http://localhost:8001",
                "project_uuid": "project-123",
                "user_email": "user@example.com",
            }
        )
    )

    with pytest.raises(SystemExit, match="Bearer-token auth is not supported"):
        config_module.load_config()


def test_load_config_fails_without_api_key(isolated_config):
    config_dir, config_file = isolated_config
    config_dir.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "api_url": "http://localhost:8001",
                "project_uuid": "project-123",
                "user_email": "user@example.com",
            }
        )
    )

    with pytest.raises(SystemExit, match="No API key configured"):
        config_module.load_config()
