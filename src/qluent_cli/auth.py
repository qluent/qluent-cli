"""Browser-based SSO login flow for the Qluent CLI."""

from __future__ import annotations

import secrets
import socket
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import click

LOGIN_TIMEOUT_SECONDS = 300  # 5 minutes
LOGIN_PATH = "/cli-auth"

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html><head><title>Qluent CLI</title>
<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;\
align-items:center;min-height:100vh;margin:0;background:#f8f9fa}\
.card{text-align:center;padding:2rem;border-radius:8px;background:#fff;\
box-shadow:0 2px 8px rgba(0,0,0,0.1);max-width:400px}\
h1{color:#16a34a;margin-bottom:0.5rem}p{color:#374151}</style>
</head><body><div class="card">
<h1>Logged in</h1>
<p>You can close this tab and return to the terminal.</p>
</div></body></html>
"""

_ERROR_HTML_TEMPLATE = (
    '<!DOCTYPE html><html><head><title>Qluent CLI</title>'
    "<style>body{font-family:system-ui,sans-serif;display:flex;justify-content:center;"
    "align-items:center;min-height:100vh;margin:0;background:#f8f9fa}"
    ".card{text-align:center;padding:2rem;border-radius:8px;background:#fff;"
    "box-shadow:0 2px 8px rgba(0,0,0,0.1);max-width:400px}"
    "h1{color:#dc2626;margin-bottom:0.5rem}p{color:#374151}</style>"
    '</head><body><div class="card">'
    "<h1>Login failed</h1>"
    "<p>%s</p>"
    "</div></body></html>"
)


@dataclass
class CallbackResult:
    """Result from the browser callback."""

    success: bool
    api_key: str = ""
    project_uuid: str = ""
    user_email: str = ""
    error: str = ""


def _single(values: list[str] | None) -> str:
    """Extract a single value from a query-parameter list, or empty string."""
    if not values:
        return ""
    return values[0]


def _find_free_port() -> int:
    """Find a free port on 127.0.0.1 by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handle the OAuth-style callback from qluent-ui."""

    server: _CallbackServer  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "Not found")
            return

        params = parse_qs(parsed.query)

        # Validate CSRF state token
        state = _single(params.get("state"))
        if state != self.server.expected_state:
            self._respond_html(
                400,
                _ERROR_HTML_TEMPLATE % "Invalid state parameter. Please try again.",
            )
            self.server.result = CallbackResult(
                success=False, error="State mismatch (possible CSRF)"
            )
            self.server.got_callback.set()
            return

        # Check for error response from the auth server
        error = _single(params.get("error"))
        if error:
            error_desc = _single(params.get("error_description")) or error
            self._respond_html(400, _ERROR_HTML_TEMPLATE % error_desc)
            self.server.result = CallbackResult(success=False, error=error_desc)
            self.server.got_callback.set()
            return

        # Extract credentials
        api_key = _single(params.get("api_key"))
        project_uuid = _single(params.get("project_uuid"))
        user_email = _single(params.get("user_email"))

        if not all([api_key, project_uuid, user_email]):
            missing = [
                name
                for name, val in [
                    ("api_key", api_key),
                    ("project_uuid", project_uuid),
                    ("user_email", user_email),
                ]
                if not val
            ]
            msg = f"Missing parameters: {', '.join(missing)}"
            self._respond_html(400, _ERROR_HTML_TEMPLATE % msg)
            self.server.result = CallbackResult(success=False, error=msg)
            self.server.got_callback.set()
            return

        self._respond_html(200, _SUCCESS_HTML)
        self.server.result = CallbackResult(
            success=True,
            api_key=api_key,
            project_uuid=project_uuid,
            user_email=user_email,
        )
        self.server.got_callback.set()

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def _respond_html(self, status: int, html: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""


class _CallbackServer(HTTPServer):
    """Local HTTP server that waits for the auth callback."""

    def __init__(self, port: int, expected_state: str) -> None:
        super().__init__(("127.0.0.1", port), _CallbackHandler)
        self.expected_state = expected_state
        self.result: CallbackResult | None = None
        self.got_callback = threading.Event()


def _api_url_to_ui_url(api_url: str) -> str:
    """Derive the UI base URL from the API base URL.

    Production: https://api.app.qluent.com -> https://app.qluent.com
    Local:      http://localhost:8001      -> http://localhost:3000
    """
    normalized = api_url.rstrip("/").lower()
    if normalized.startswith("http://localhost") or normalized.startswith(
        "http://127.0.0.1"
    ):
        return "http://localhost:3000"
    return api_url.replace("api.app.", "app.").rstrip("/")


def browser_login(api_url: str) -> CallbackResult:
    """Run the browser-based login flow. Returns credentials or error."""
    state = secrets.token_urlsafe(32)
    port = _find_free_port()
    callback_url = f"http://127.0.0.1:{port}/callback"

    ui_base = _api_url_to_ui_url(api_url)
    login_url = (
        f"{ui_base}{LOGIN_PATH}?"
        + urlencode({"callback_url": callback_url, "state": state})
    )

    server = _CallbackServer(port, expected_state=state)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        click.echo("Opening browser to log in...")
        opened = webbrowser.open(login_url)
        if not opened:
            click.echo(
                "\nCould not open browser automatically. "
                "Open this URL in your browser:\n"
            )
        else:
            click.echo("If the browser did not open, copy this URL:\n")
        click.echo(f"  {login_url}\n")
        click.echo("Waiting for login...")

        got_it = server.got_callback.wait(timeout=LOGIN_TIMEOUT_SECONDS)
        if not got_it:
            return CallbackResult(
                success=False,
                error=f"Login timed out after {LOGIN_TIMEOUT_SECONDS} seconds.",
            )

        return server.result or CallbackResult(
            success=False, error="No result received."
        )
    finally:
        server.shutdown()
