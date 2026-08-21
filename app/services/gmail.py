"""Gmail API client (Python port).

Mirrors the OAuth flow used by `admob.py` but hits the Gmail API instead.
"""

from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

import httpx

OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
DEFAULT_TIMEOUT = 30.0
TOKEN_REFRESH_SKEW_MS = 5 * 60 * 1000

# Heuristics for filtering out non-user emails (Google security alerts, etc.)
SYSTEM_EMAIL_PATTERNS = (
    "no-reply@accounts.google.com",
    "@google.com",
)
SYSTEM_SUBJECT_PATTERNS = (
    "security alert",
    "2-step verification",
    "recovered successfully",
    "sign-in",
    "new device",
)


class GmailConfigError(RuntimeError):
    """Missing required env var."""


class GmailAPIError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"gmail api {status_code}: {body}")
        self.status_code = status_code
        self.body = body


@dataclass
class GmailCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str = ""
    expiry_date_ms: int = 0

    @classmethod
    def from_env(cls) -> "GmailCredentials":
        try:
            return cls(
                client_id=os.environ["GMAIL_CLIENT_ID"],
                client_secret=os.environ["GMAIL_CLIENT_SECRET"],
                refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
                access_token=os.environ.get("GMAIL_ACCESS_TOKEN", ""),
                expiry_date_ms=int(os.environ.get("GMAIL_EXPIRY_DATE", "0")),
            )
        except KeyError as exc:
            missing = exc.args[0]
            raise GmailConfigError(f"missing required env var: {missing}") from exc


@dataclass
class EmailMessage:
    id: str
    thread_id: str
    subject: str
    from_: str
    date: datetime
    body: str
    snippet: str
    is_system: bool

    def issue_title(self) -> str:
        return f"[用户反馈] {self.subject}"


class GmailClient:
    """Async Gmail client with automatic OAuth refresh."""

    def __init__(self, credentials: GmailCredentials | None = None) -> None:
        self.creds = credentials or GmailCredentials.from_env()
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GmailClient":
        self._http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ----- auth -----

    async def _refresh_access_token(self) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                OAUTH_TOKEN_URL,
                data={
                    "client_id": self.creds.client_id,
                    "client_secret": self.creds.client_secret,
                    "refresh_token": self.creds.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if response.status_code != 200:
            raise GmailAPIError(response.status_code, response.text)
        data = response.json()
        if "access_token" not in data:
            raise GmailAPIError(500, f"no access_token in response: {data}")
        self.creds.access_token = data["access_token"]
        self.creds.expiry_date_ms = int(time.time() * 1000) + data["expires_in"] * 1000

    async def _ensure_token(self) -> str:
        now_ms = int(time.time() * 1000)
        if not self.creds.access_token or now_ms >= self.creds.expiry_date_ms - TOKEN_REFRESH_SKEW_MS:
            await self._refresh_access_token()
        return self.creds.access_token

    # ----- low-level -----

    async def _get(self, path: str, params: dict | None = None) -> dict:
        if self._http is None:
            raise RuntimeError("GmailClient must be used as an async context manager")
        token = await self._ensure_token()
        response = await self._http.get(
            f"{GMAIL_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        if response.status_code != 200:
            raise GmailAPIError(response.status_code, response.text)
        return response.json()

    # ----- messages -----

    async def list_inbox(self, max_results: int = 30, query: str | None = None) -> list[dict]:
        params: dict[str, Any] = {
            "labelIds": "INBOX",
            "maxResults": max_results,
        }
        if query:
            params["q"] = query
        data = await self._get("/users/me/messages", params)
        return data.get("messages") or []

    async def get_message(self, message_id: str) -> EmailMessage:
        data = await self._get(f"/users/me/messages/{message_id}", {"format": "full"})
        return self._parse_message(data)

    # ----- parsing -----

    @staticmethod
    def _decode_body(data_part: dict) -> str:
        body_data = data_part.get("body", {}).get("data")
        if body_data:
            return _b64url_decode(body_data)
        parts = data_part.get("parts") or []
        for part in parts:
            if part.get("mimeType") == "text/plain":
                if part.get("body", {}).get("data"):
                    return _b64url_decode(part["body"]["data"])
        # fallback: first part with body
        for part in parts:
            if part.get("body", {}).get("data"):
                return _b64url_decode(part["body"]["data"])
        return ""

    def _parse_message(self, data: dict) -> EmailMessage:
        headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "(无主题)")
        from_ = headers.get("from", "(无发件人)")
        date_raw = headers.get("date", "")
        try:
            date = parsedate_to_datetime(date_raw).astimezone(timezone.utc)
        except (TypeError, ValueError):
            date = datetime.now(timezone.utc)

        body = self._decode_body(data.get("payload", {})).strip()
        body = body[:500]
        snippet = data.get("snippet", "")

        return EmailMessage(
            id=data["id"],
            thread_id=data.get("threadId", ""),
            subject=subject,
            from_=from_,
            date=date,
            body=body,
            snippet=snippet,
            is_system=_is_system_email(from_, subject),
        )


def _b64url_decode(value: str) -> str:
    """Gmail uses URL-safe base64 with padding stripped."""
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - defensive
        return ""


def _is_system_email(from_: str, subject: str) -> bool:
    sender_l = from_.lower()
    subject_l = subject.lower()
    if any(p in sender_l for p in SYSTEM_EMAIL_PATTERNS):
        return True
    if any(p in subject_l for p in SYSTEM_SUBJECT_PATTERNS):
        return True
    return False


# ----- state -----

class FeedbackState:
    """Persisted set of seen email ids + sync metadata."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.seen_email_ids: list[str] = []
        self.last_sync_at: str | None = None

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json_loads_safe(fh.read())
        except FileNotFoundError:
            return
        if not data:
            return
        self.seen_email_ids = list(data.get("seenEmailIds") or [])
        self.last_sync_at = data.get("lastSyncAt")

    def save(self) -> None:
        import json
        import os
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {
            "seenEmailIds": self.seen_email_ids[-1000:],  # cap retention
            "lastSyncAt": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        self.last_sync_at = payload["lastSyncAt"]

    def is_seen(self, message_id: str) -> bool:
        return message_id in self.seen_email_ids

    def mark_seen(self, message_id: str) -> None:
        if message_id not in self.seen_email_ids:
            self.seen_email_ids.append(message_id)

    def reset(self) -> None:
        self.seen_email_ids = []


def json_loads_safe(text: str) -> dict | None:
    import json
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except (ValueError, TypeError):
        return None