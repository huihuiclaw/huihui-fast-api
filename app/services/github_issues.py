"""Lightweight GitHub REST client for issue creation + lookup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


class GitHubConfigError(RuntimeError):
    """Missing required env var."""


class GitHubAPIError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"github api {status_code}: {body}")
        self.status_code = status_code
        self.body = body


@dataclass
class GitHubConfig:
    token: str
    repo: str  # "owner/name"

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        try:
            token = os.environ["FEEDBACK_GH_TOKEN"]
            repo = os.environ["TARGET_REPO"]
        except KeyError as exc:
            raise GitHubConfigError(f"missing required env var: {exc.args[0]}") from exc
        return cls(token=token, repo=repo)


class GitHubClient:
    def __init__(self, config: GitHubConfig | None = None) -> None:
        self.config = config or GitHubConfig.from_env()
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GitHubClient":
        self._http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "huihui-fast-api",
        }

    async def find_open_issue_with_title(self, title: str) -> dict | None:
        """Return the first open issue matching `title`, else None."""
        if self._http is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")
        page = 1
        while True:
            response = await self._http.get(
                f"{GITHUB_API_BASE}/repos/{self.config.repo}/issues",
                headers=self._headers,
                params={"state": "open", "per_page": 100, "page": page},
            )
            if response.status_code != 200:
                raise GitHubAPIError(response.status_code, response.text)
            issues = response.json()
            if not issues:
                return None
            for issue in issues:
                # Skip PRs (they show up in /issues too)
                if "pull_request" in issue:
                    continue
                if issue.get("title") == title:
                    return issue
            if len(issues) < 100:
                return None
            page += 1

    async def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict:
        if self._http is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        response = await self._http.post(
            f"{GITHUB_API_BASE}/repos/{self.config.repo}/issues",
            headers=self._headers,
            json=payload,
        )
        if response.status_code not in (200, 201):
            raise GitHubAPIError(response.status_code, response.text)
        return response.json()