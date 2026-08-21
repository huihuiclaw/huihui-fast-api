"""AdMob API client (Python port).

Reads OAuth credentials and publisher id from environment variables so the
service can be deployed with secrets managed externally (GitHub Secrets,
Kubernetes secrets, etc.) instead of baking them into the image.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

ADMob_API_BASE = "https://admob.googleapis.com/v1beta"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_TIMEOUT = 30.0
TOKEN_REFRESH_SKEW_MS = 5 * 60 * 1000  # refresh 5 minutes before expiry


class AdMobConfigError(RuntimeError):
    """Raised when required AdMob configuration is missing."""


class AdMobAPIError(RuntimeError):
    """Raised when the AdMob API returns an error response."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"admob api {status_code}: {body}")
        self.status_code = status_code
        self.body = body


@dataclass
class AdMobCredentials:
    """OAuth credentials loaded from environment."""

    client_id: str
    client_secret: str
    refresh_token: str
    publisher_id: str
    access_token: str = ""
    expiry_date_ms: int = 0

    @classmethod
    def from_env(cls) -> "AdMobCredentials":
        try:
            return cls(
                client_id=os.environ["ADMOB_CLIENT_ID"],
                client_secret=os.environ["ADMOB_CLIENT_SECRET"],
                refresh_token=os.environ["ADMOB_REFRESH_TOKEN"],
                publisher_id=os.environ["ADMOB_PUBLISHER_ID"],
                access_token=os.environ.get("ADMOB_ACCESS_TOKEN", ""),
                expiry_date_ms=int(os.environ.get("ADMOB_EXPIRY_DATE", "0")),
            )
        except KeyError as exc:
            missing = exc.args[0]
            raise AdMobConfigError(
                f"missing required env var: {missing}"
            ) from exc


class AdMobClient:
    """Async AdMob client with automatic OAuth refresh."""

    def __init__(self, credentials: AdMobCredentials | None = None) -> None:
        self.creds = credentials or AdMobCredentials.from_env()
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AdMobClient":
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
            raise AdMobAPIError(response.status_code, response.text)
        data = response.json()
        if "access_token" not in data:
            raise AdMobAPIError(500, f"no access_token in response: {data}")
        self.creds.access_token = data["access_token"]
        self.creds.expiry_date_ms = int(time.time() * 1000) + data["expires_in"] * 1000

    async def _ensure_token(self) -> None:
        now_ms = int(time.time() * 1000)
        if not self.creds.access_token or now_ms >= self.creds.expiry_date_ms - TOKEN_REFRESH_SKEW_MS:
            await self._refresh_access_token()

    # ----- reports -----

    async def generate_report(self, days: int = 7) -> list[dict[str, Any]]:
        """Fetch a per-day earnings report for the last `days` days."""
        if self._http is None:
            raise RuntimeError("AdMobClient must be used as an async context manager")
        await self._ensure_token()

        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days)

        payload = {
            "reportSpec": {
                "dateRange": {
                    "startDate": {"year": start.year, "month": start.month, "day": start.day},
                    "endDate": {"year": today.year, "month": today.month, "day": today.day},
                },
                "dimensions": ["DATE"],
                "metrics": ["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS"],
                "localizationSettings": {"currencyCode": "USD"},
            }
        }

        response = await self._http.post(
            f"{ADMob_API_BASE}/accounts/{self.creds.publisher_id}/networkReport:generate",
            headers={"Authorization": f"Bearer {self.creds.access_token}"},
            json=payload,
        )
        if response.status_code != 200:
            raise AdMobAPIError(response.status_code, response.text)
        return response.json()