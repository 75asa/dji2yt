"""OAuth credentials for Drive / YouTube / Calendar."""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    # Full Drive scope is required to rename files the DJI app uploaded.
    "https://www.googleapis.com/auth/drive",
    # Upload + playlist management.
    "https://www.googleapis.com/auth/youtube",
    # Read-only, used by plugins (e.g. tennis) to classify by calendar events.
    "https://www.googleapis.com/auth/calendar.readonly",
]


def run_login(client_secret: Path, token_path: Path) -> Credentials:
    """Interactive browser login. Run once on a machine with a browser."""
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def load_credentials(token_path: Path) -> Credentials:
    if not token_path.exists():
        raise SystemExit(f"{token_path} not found. Run `dji2yt auth` first.")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise SystemExit("Stored credentials are invalid. Run `dji2yt auth` again.")
    return creds
