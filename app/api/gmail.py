"""Gmail feedback endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.services.gmail import (
    EmailMessage,
    FeedbackState,
    GmailAPIError,
    GmailClient,
    GmailConfigError,
)
from app.services.github_issues import GitHubAPIError, GitHubClient, GitHubConfigError

router = APIRouter(prefix="/gmail", tags=["gmail"])

STATE_PATH = os.environ.get("GMAIL_STATE_PATH", "/data/gmail_feedback_state.json")
DEFAULT_QUERY = os.environ.get("GMAIL_DEFAULT_QUERY", "subject:solat OR subject:prayer OR subject:malaysia")
MAX_BODY_CHARS = 500


def _format_issue_body(msg: EmailMessage) -> str:
    return (
        f"**用户反馈**\n\n"
        f"- **发件人:** {msg.from_}\n"
        f"- **日期:** {msg.date.isoformat()}\n"
        f"- **主题:** {msg.subject}\n\n"
        f"---\n\n"
        f"**反馈内容:**\n{msg.body[:MAX_BODY_CHARS]}\n\n"
        f"---\n"
        f"*🤖 自动创建自邮件监控*"
    )


async def _scan_and_create(
    *,
    max_results: int,
    query: str | None,
    create_issues: bool,
) -> dict:
    state = FeedbackState(STATE_PATH)
    state.load()

    summary = {
        "scanned": 0,
        "new": 0,
        "skipped_seen": 0,
        "skipped_system": 0,
        "skipped_existing_issue": 0,
        "created": [],
        "errors": [],
    }

    try:
        async with GmailClient() as gmail, GitHubClient() as gh:
            try:
                messages = await gmail.list_inbox(max_results=max_results, query=query)
            except GmailAPIError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

            for stub in messages:
                summary["scanned"] += 1
                msg_id = stub["id"]
                if state.is_seen(msg_id):
                    summary["skipped_seen"] += 1
                    continue

                try:
                    msg = await gmail.get_message(msg_id)
                except GmailAPIError as exc:
                    summary["errors"].append({"email_id": msg_id, "stage": "fetch", "error": str(exc)})
                    state.mark_seen(msg_id)
                    continue

                if msg.is_system:
                    summary["skipped_system"] += 1
                    state.mark_seen(msg_id)
                    continue

                title = msg.issue_title()
                summary["new"] += 1

                if not create_issues:
                    state.mark_seen(msg_id)
                    summary["created"].append({
                        "email_id": msg.id,
                        "subject": msg.subject,
                        "from": msg.from_,
                        "would_create_issue": title,
                        "dry_run": True,
                    })
                    continue

                try:
                    existing = await gh.find_open_issue_with_title(title)
                except (GitHubAPIError, GitHubConfigError) as exc:
                    summary["errors"].append({"email_id": msg_id, "stage": "gh_lookup", "error": str(exc)})
                    state.mark_seen(msg_id)
                    continue

                if existing:
                    summary["skipped_existing_issue"] += 1
                    state.mark_seen(msg_id)
                    continue

                try:
                    issue = await gh.create_issue(title, _format_issue_body(msg), ["user-feedback"])
                except (GitHubAPIError, GitHubConfigError) as exc:
                    summary["errors"].append({"email_id": msg_id, "stage": "gh_create", "error": str(exc)})
                    state.mark_seen(msg_id)
                    continue

                summary["created"].append({
                    "email_id": msg.id,
                    "subject": msg.subject,
                    "from": msg.from_,
                    "issue_number": issue.get("number"),
                    "issue_url": issue.get("html_url"),
                })
                state.mark_seen(msg_id)
    except GmailConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GitHubConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    state.save()
    summary["last_sync_at"] = state.last_sync_at
    summary["dry_run"] = not create_issues
    summary["query"] = query
    summary["max_results"] = max_results
    summary["state_path"] = STATE_PATH
    summary["seen_total"] = len(state.seen_email_ids)
    return summary


@router.get("/feedback")
async def list_feedback(
    max: int = Query(default=30, ge=1, le=200),
    query: str | None = Query(default=None, description="Gmail search query"),
) -> dict:
    """Dry-run: scan inbox and report what would be created, without touching GitHub."""
    return await _scan_and_create(max_results=max, query=query, create_issues=False)


@router.post("/feedback/sync")
async def sync_feedback(
    max: int = Query(default=30, ge=1, le=200),
    query: str | None = Query(default=None),
) -> dict:
    """Scan inbox and create GitHub Issues for any new user feedback."""
    return await _scan_and_create(max_results=max, query=query, create_issues=True)


@router.get("/feedback/state")
async def feedback_state() -> dict:
    state = FeedbackState(STATE_PATH)
    state.load()
    return {
        "path": STATE_PATH,
        "seen_total": len(state.seen_email_ids),
        "last_sync_at": state.last_sync_at,
        "seen_email_ids_tail": state.seen_email_ids[-10:],
    }


@router.post("/feedback/reset")
async def reset_feedback_state() -> dict:
    """Clear processed-email memory so the next sync re-scans everything."""
    state = FeedbackState(STATE_PATH)
    state.load()
    previous = len(state.seen_email_ids)
    state.reset()
    state.save()
    return {
        "reset": True,
        "previously_seen": previous,
        "path": STATE_PATH,
    }