from __future__ import annotations

import json
import webbrowser
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from phase0.artifacts import ensure_dir
from phase0.config import Settings
from phase0.models import SessionState
from phase0.time_utils import indian_timezone


IST = indian_timezone()

AUTH_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
PROFILE_URL = "https://api.upstox.com/v2/user/profile"


def authenticate_interactive(settings: Settings, open_browser: bool = True) -> SessionState:
    state: Dict[str, Optional[str]] = {"code": None}

    handler = _build_callback_handler(state)
    parsed = urlparse(settings.upstox_redirect_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    server = HTTPServer((host, port), handler)

    params = urlencode({
        "client_id": settings.upstox_api_key,
        "redirect_uri": settings.upstox_redirect_url,
        "response_type": "code",
    })
    login_url = "%s?%s" % (AUTH_DIALOG_URL, params)

    print("Starting local callback server on %s" % settings.upstox_redirect_url)

    if open_browser:
        webbrowser.open(login_url)
    else:
        print("Open this URL manually:\n%s" % login_url)

    print("Waiting for Upstox login callback...")
    server.handle_request()
    server.server_close()

    code = state["code"]
    if not code:
        raise RuntimeError("No authorization code received from Upstox callback.")

    token_response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.upstox_api_key,
            "client_secret": settings.upstox_api_secret,
            "redirect_uri": settings.upstox_redirect_url,
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if token_response.status_code != 200:
        raise RuntimeError("Token exchange failed: %s" % token_response.text[:300])

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("No access_token in token response: %s" % json.dumps(token_data)[:300])

    profile = _fetch_profile(access_token)
    login_time = datetime.now(IST)

    session_state = SessionState(
        access_token=access_token,
        user_id=profile.get("user_id") or profile.get("client_id") or "",
        user_name=profile.get("user_name") or "",
        provider="upstox",
        email=profile.get("email"),
        login_time=login_time,
        expires_at=_next_session_expiry(login_time),
    )
    save_session_state(settings, session_state)
    return session_state


def exchange_code_for_session(settings: Settings, code: str) -> SessionState:
    token_response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.upstox_api_key,
            "client_secret": settings.upstox_api_secret,
            "redirect_uri": settings.upstox_redirect_url,
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if token_response.status_code != 200:
        raise RuntimeError("Token exchange failed: %s" % token_response.text[:300])

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("No access_token in token response: %s" % json.dumps(token_data)[:300])

    profile = _fetch_profile(access_token)
    login_time = datetime.now(IST)

    session_state = SessionState(
        access_token=access_token,
        user_id=profile.get("user_id") or profile.get("client_id") or "",
        user_name=profile.get("user_name") or "",
        provider="upstox",
        email=profile.get("email"),
        login_time=login_time,
        expires_at=_next_session_expiry(login_time),
    )
    save_session_state(settings, session_state)
    return session_state


def load_session_state(settings: Settings) -> Optional[SessionState]:
    path = settings.session_state_path
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("provider", "upstox") != settings.provider:
        return None
    return SessionState(
        access_token=payload["access_token"],
        user_id=payload["user_id"],
        user_name=payload["user_name"],
        provider=payload.get("provider", "upstox"),
        email=payload.get("email"),
        login_time=datetime.fromisoformat(payload["login_time"]),
        expires_at=datetime.fromisoformat(payload["expires_at"]),
    )


def save_session_state(settings: Settings, state: SessionState) -> Path:
    ensure_dir(settings.session_state_path.parent)
    payload = {
        "access_token": state.access_token,
        "user_id": state.user_id,
        "user_name": state.user_name,
        "provider": state.provider,
        "email": state.email,
        "login_time": state.login_time.isoformat(),
        "expires_at": state.expires_at.isoformat(),
    }
    settings.session_state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return settings.session_state_path


def clear_session_state(settings: Settings) -> None:
    path = settings.session_state_path
    if path.exists():
        path.unlink()


def ensure_valid_session(settings: Settings) -> SessionState:
    session_state = load_session_state(settings)
    if not session_state:
        raise RuntimeError("Saved Upstox session not found. Run `python phase0_probe.py auth` first.")

    now = datetime.now(IST)
    if session_state.expires_at <= now:
        clear_session_state(settings)
        raise RuntimeError("Saved Upstox session has expired. Run `python phase0_probe.py auth` again.")

    try:
        _fetch_profile(session_state.access_token)
    except Exception as exc:
        clear_session_state(settings)
        raise RuntimeError("Saved Upstox session is invalid. Run `python phase0_probe.py auth` again.") from exc

    return session_state


def _fetch_profile(access_token: str) -> Dict:
    response = requests.get(
        PROFILE_URL,
        headers={"Authorization": "Bearer %s" % access_token, "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code != 200:
        raise RuntimeError("Profile fetch failed (%s): %s" % (response.status_code, response.text[:200]))
    data = response.json()
    return data.get("data") or data


def _next_session_expiry(login_time: datetime) -> datetime:
    next_day = login_time.astimezone(IST).date() + timedelta(days=1)
    return datetime.combine(next_day, time(hour=6, minute=0), tzinfo=IST)


def _build_callback_handler(state: Dict[str, Optional[str]]):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            code = query.get("code", [None])[0]

            if code:
                state["code"] = code
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:Arial;padding:24px;'>"
                    b"<h2>Login successful</h2>"
                    b"<p>Authorization code received. You can close this tab.</p>"
                    b"</body></html>"
                )
                return

            error = query.get("error", [None])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            body = (
                "<html><body style='font-family:Arial;padding:24px;'>"
                "<h2>Login callback reached, but no code was found</h2>"
                "<p>Error: %s</p><p>Query: %s</p></body></html>"
            ) % (error, parsed.query)
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args) -> None:
            return

    return CallbackHandler
