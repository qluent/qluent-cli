"""Configuration management — ~/.qluent/config.json + env var fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".qluent"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class QluentConfig:
    api_key: str
    api_url: str
    project_uuid: str
    user_email: str


def load_config() -> QluentConfig:
    """Load config from env vars, falling back to ~/.qluent/config.json."""
    file_config: dict[str, str] = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            file_config = json.load(f)

    def get(env_var: str, file_key: str) -> str:
        return os.environ.get(env_var) or file_config.get(file_key, "")

    api_key = get("QLUENT_API_KEY", "api_key")
    api_url = get("QLUENT_API_URL", "api_url") or "https://api.qluent.io"
    project_uuid = get("QLUENT_PROJECT_UUID", "project_uuid")
    user_email = get("QLUENT_USER_EMAIL", "user_email")

    if not api_key:
        raise SystemExit("No API key configured. Run: qluent config --api-key qk_...")
    if not project_uuid:
        raise SystemExit("No project configured. Run: qluent config --project UUID")
    if not user_email:
        raise SystemExit("No email configured. Run: qluent config --email you@co.com")

    return QluentConfig(
        api_key=api_key,
        api_url=api_url.rstrip("/"),
        project_uuid=project_uuid,
        user_email=user_email,
    )


def save_config(
    api_key: str | None = None,
    api_url: str | None = None,
    project_uuid: str | None = None,
    user_email: str | None = None,
) -> dict[str, str]:
    """Save config values to ~/.qluent/config.json (merges with existing)."""
    existing: dict[str, str] = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            existing = json.load(f)

    if api_key is not None:
        existing["api_key"] = api_key
    if api_url is not None:
        existing["api_url"] = api_url
    if project_uuid is not None:
        existing["project_uuid"] = project_uuid
    if user_email is not None:
        existing["user_email"] = user_email

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    return existing
