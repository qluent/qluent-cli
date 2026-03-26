"""Configuration management — ~/.qluent/config.json + env var fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".qluent"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_API_URL = "https://app-development.qluent.com"
LOCAL_API_URL = "http://localhost:8001"


@dataclass
class QluentConfig:
    api_key: str
    api_url: str
    project_uuid: str
    user_email: str
    client_safe: bool = False


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def default_client_safe(api_url: str) -> bool:
    normalized = api_url.rstrip("/").lower()
    return not (
        normalized.startswith("http://localhost")
        or normalized.startswith("http://127.0.0.1")
    )


def load_config() -> QluentConfig:
    """Load config from env vars, falling back to ~/.qluent/config.json."""
    file_config: dict[str, Any] = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            file_config = json.load(f)

    def get(env_var: str, file_key: str) -> Any:
        return os.environ.get(env_var) or file_config.get(file_key, "")

    api_key = get("QLUENT_API_KEY", "api_key")
    api_url = get("QLUENT_API_URL", "api_url") or DEFAULT_API_URL
    project_uuid = get("QLUENT_PROJECT_UUID", "project_uuid")
    user_email = get("QLUENT_USER_EMAIL", "user_email")
    if "QLUENT_CLIENT_SAFE" in os.environ:
        client_safe = _parse_bool(os.environ["QLUENT_CLIENT_SAFE"])
    elif "client_safe" in file_config:
        client_safe = _parse_bool(file_config["client_safe"])
    else:
        client_safe = default_client_safe(api_url)

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
        client_safe=client_safe,
    )


def save_config(
    api_key: str | None = None,
    api_url: str | None = None,
    project_uuid: str | None = None,
    user_email: str | None = None,
    client_safe: bool | None = None,
) -> dict[str, Any]:
    """Save config values to ~/.qluent/config.json (merges with existing)."""
    existing: dict[str, Any] = {}
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
    if client_safe is not None:
        existing["client_safe"] = client_safe

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    with open(CONFIG_FILE, "w") as f:
        json.dump(existing, f, indent=2)
    CONFIG_FILE.chmod(0o600)

    return existing


def mask_key(value: str) -> str:
    """Mask an API key for display: show first 10 chars + '...'."""
    return value[:10] + "..." if len(value) > 10 else value
