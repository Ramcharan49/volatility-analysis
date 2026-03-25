from __future__ import annotations

import json
import webbrowser
from datetime import datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from kiteconnect import KiteConnect

from phase0.artifacts import ensure_dir
from phase0.config import Settings, load_settings
from phase0.models import KiteSessionState
from phase0.time_utils import indian_timezone


IST = indian_timezone()


def build_kite_client(settings: Settings, access_token: Optional[str] = None) -> KiteConnect:
    kite = KiteConnect(api_key=settings.kite_api_key)
    if access_token:
        kite.set_access_token(access_token)
    return kite


def authenticate_interactive(settings: Settings, open_browser: bool = True) -> KiteSessionState:
    state = {"request_token": None}
    kite = build_kite_client(settings)
    login_url = kite.login_url()

    handler = _build_callback_handler(settings.callback_path, state)
    server = HTTPServer((settings.callback_host, settings.callback_port), handler)

    print("Starting local callback server on %s" % settings.kite_redirect_url)
    print("Make sure the registered redirect URL in Kite Connect matches exactly.")

    if open_browser:
        webbrowser.open(login_url)
    else:
        print("Open this URL manually:\n%s" % login_url)

    print("Waiting for Zerodha login callback...")
    server.handle_request()
    server.server_close()

    request_token = state["request_token"]
    if not request_token:
        raise RuntimeError("No request_token received from Zerodha callback.")

    session = kite.generate_session(request_token, api_secret=settings.kite_api_secret)
    access_token = session["access_token"]
    kite.set_access_token(access_token)
    profile = kite.profile()

    login_time = datetime.now(IST)
    session_state = KiteSessionState(
        access_token=access_token,
        user_id=profile.get("user_id") or "",
        user_name=profile.get("user_name") or "",
        email=profile.get("email"),
        login_time=login_time,
        expires_at=_next_session_expiry(login_time),
    )
    save_session_state(settings, session_state)
    return session_state


def load_session_state(settings: Settings) -> Optional[KiteSessionState]:
    path = settings.session_state_path
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    return KiteSessionState(
        access_token=payload["access_token"],
        user_id=payload["user_id"],
        user_name=payload["user_name"],
        email=payload.get("email"),
        login_time=datetime.fromisoformat(payload["login_time"]),
        expires_at=datetime.fromisoformat(payload["expires_at"]),
    )


def clear_session_state(settings: Settings) -> None:
    path = settings.session_state_path
    if path.exists():
        path.unlink()


def ensure_valid_session(settings: Settings) -> Tuple[KiteSessionState, KiteConnect, Dict]:
    session_state = load_session_state(settings)
    if not session_state:
        raise RuntimeError("Saved Zerodha session not found. Run `python phase0_probe.py auth` again.")

    now = datetime.now(IST)
    if session_state.expires_at <= now:
        clear_session_state(settings)
        raise RuntimeError("Saved Zerodha session has expired. Run `python phase0_probe.py auth` again.")

    kite = build_kite_client(settings, session_state.access_token)
    try:
        profile = kite.profile()
    except Exception as exc:
        clear_session_state(settings)
        raise RuntimeError("Saved Zerodha session is invalid. Run `python phase0_probe.py auth` again.") from exc

    return session_state, kite, profile


def save_session_state(settings: Settings, state: KiteSessionState) -> Path:
    ensure_dir(settings.session_state_path.parent)
    payload = {
        "access_token": state.access_token,
        "user_id": state.user_id,
        "user_name": state.user_name,
        "email": state.email,
        "login_time": state.login_time.isoformat(),
        "expires_at": state.expires_at.isoformat(),
    }
    settings.session_state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return settings.session_state_path


def main() -> int:
    settings = load_settings()
    session_state = authenticate_interactive(settings)
    print("\nSUCCESS")
    print("Authenticated successfully.")
    print("User ID   : %s" % session_state.user_id)
    print("Name      : %s" % session_state.user_name)
    print("Email     : %s" % (session_state.email or ""))
    print("Token saved to %s" % settings.session_state_path)
    print("Token valid until approximately %s" % session_state.expires_at.isoformat())
    return 0


def _next_session_expiry(login_time: datetime) -> datetime:
    next_day = login_time.astimezone(IST).date() + timedelta(days=1)
    return datetime.combine(next_day, time(hour=6, minute=0), tzinfo=IST)


def _build_callback_handler(callback_path: str, state: Dict[str, Optional[str]]):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path != callback_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            query = parse_qs(parsed.query)
            request_token = query.get("request_token", [None])[0]
            status = query.get("status", [None])[0]

            if request_token:
                state["request_token"] = request_token
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:Arial;padding:24px;'>"
                    b"<h2>Login successful</h2>"
                    b"<p>request_token received. You can close this tab.</p>"
                    b"</body></html>"
                )
                return

            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            body = (
                "<html><body style='font-family:Arial;padding:24px;'>"
                "<h2>Login callback reached, but no request_token was found</h2>"
                "<p>Status: %s</p><p>Query: %s</p></body></html>"
            ) % (status, parsed.query)
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args) -> None:
            return

    return CallbackHandler


if __name__ == "__main__":
    raise SystemExit(main())
