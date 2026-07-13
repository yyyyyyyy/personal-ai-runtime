"""Inbox email projection read ports."""

from __future__ import annotations

from typing import Any

from app.core.runtime.read_ports._common import kernel


def query_recent_inbox_emails(*, limit: int = 20) -> list[dict[str, Any]]:
    return kernel().query_state(
        "inbox_emails",
        status_not="archived",
        limit=limit,
        order="date_desc",
    )


def search_inbox_emails(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    return kernel().query_state(
        "inbox_emails",
        search=query,
        limit=limit,
        order="date_desc",
    )


def query_pending_inbox_emails(*, limit: int = 50) -> list[dict[str, Any]]:
    """Pending inbox rows — state gate for email backlog reactions / nudges."""
    return kernel().query_state(
        "inbox_emails", status="pending", limit=limit, order="date_desc",
    )


def query_inbox_email(email_id: str) -> dict[str, Any] | None:
    rows = kernel().query_state("inbox_emails", id=email_id, limit=1)
    return rows[0] if rows else None


def query_inbox_emails(
    *,
    category: str | None = None,
    status: str | None = None,
    digested: int | None = None,
    limit: int = 50,
    order: str = "date_desc",
) -> list[dict[str, Any]]:
    """Flexible inbox projection reader used by product/inbox and APIs."""
    filters: dict[str, Any] = {"limit": limit, "order": order}
    if category:
        filters["category"] = category
    if status and status != "all":
        filters["status"] = status
    if digested is not None:
        filters["digested"] = digested
    return kernel().query_state("inbox_emails", **filters)

