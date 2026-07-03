"""Proactive Inbox App — poll, classify, notify, daily digest.

App-layer interpretation only. Email fetch goes through kernel.invoke_capability.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from app.config import settings
from app.core.runtime.kernel_instance import kernel
from app.store.database import db

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = """你是一个邮件分类助手。将每封邮件分为以下类别之一：
- important: 需要用户尽快关注（老板、客户、紧急事项、验证码、账单等）
- actionable: 需要后续处理但非紧急（待办、会议邀请、项目更新等）
- ignorable: 可忽略（营销、订阅、通知类群发等）

输出严格 JSON：
{
  "emails": [
    {
      "message_id": "与输入一致",
      "category": "important|actionable|ignorable",
      "importance": 0.0-1.0,
      "reason": "一句话中文理由"
    }
  ]
}"""


def _existing_message_ids(conn) -> set[str]:
    rows = conn.execute("SELECT id FROM inbox_emails").fetchall()
    return {r["id"] for r in rows}


def _format_emails_for_llm(emails: list[dict]) -> str:
    lines = []
    for em in emails:
        lines.append(
            json.dumps(
                {
                    "message_id": em.get("message_id", ""),
                    "from": em.get("from", ""),
                    "subject": em.get("subject", ""),
                    "preview": em.get("preview", ""),
                    "date": em.get("date", ""),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


async def _classify_emails(emails: list[dict]) -> list[dict]:
    if not emails:
        return []

    from app.core.agents.llm_failover import llm_router

    client, provider = llm_router.get_client()
    user_prompt = (
        "请分类以下邮件：\n\n"
        f"{_format_emails_for_llm(emails)}\n\n"
        "请以 JSON 格式输出。"
    )

    try:
        response = await client.chat.completions.create(  # type: ignore[call-overload]
            model=provider.model,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=settings.llm_max_tokens,
        )
        raw = response.choices[0].message.content or "{}"
    except Exception as exc:
        logger.error("Inbox classification failed: %s", exc)
        return [
            {
                "message_id": em.get("message_id", ""),
                "category": "actionable",
                "importance": 0.5,
                "reason": "分类失败，默认待处理",
            }
            for em in emails
        ]

    return _parse_classification(raw, emails)


def _parse_classification(raw: str, fallback_emails: list[dict]) -> list[dict]:
    try:
        data = json.loads(raw)
        items = data.get("emails", data) if isinstance(data, dict) else data
        if isinstance(items, list) and items:
            return items
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            items = data.get("emails", [])
            if isinstance(items, list) and items:
                return items
        except json.JSONDecodeError:
            pass

    return [
        {
            "message_id": em.get("message_id", ""),
            "category": "actionable",
            "importance": 0.5,
            "reason": "无法解析分类结果",
        }
        for em in fallback_emails
    ]


def _classification_by_id(classified: list[dict]) -> dict[str, dict]:
    return {c.get("message_id", ""): c for c in classified if c.get("message_id")}


def _unread_ids_from_poll_payload(payload: dict) -> set[str]:
    """Full IMAP UNSEEN ids for read-sync; fall back to returned emails when absent."""
    explicit = payload.get("all_unread_message_ids")
    if explicit is not None:
        return {mid for mid in explicit if mid}
    emails = payload.get("emails") or []
    return {e["message_id"] for e in emails if e.get("message_id")}


def _sync_read_status(unread_ids: set[str]) -> int:
    """Mark pending emails as read when they no longer appear in IMAP UNSEEN."""
    updated = 0
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT id FROM inbox_emails
               WHERE COALESCE(status, 'pending') = 'pending'"""
        ).fetchall()
        for row in rows:
            email_id = row["id"]
            if email_id not in unread_ids:
                conn.execute(
                    "UPDATE inbox_emails SET status = 'read' WHERE id = ?",
                    (email_id,),
                )
                updated += 1
    return updated


async def apply_inbox_poll_payload(payload: dict, *, execution_id: str | None = None) -> dict:
    """Classify new emails, sync read status, store, and notify — shared by poll + handler.

    When *execution_id* is provided (background handler path), InboxEmailRecorded
    events link back to the owning Execution via caused_by.
    """
    if payload.get("error"):
        raw_error = payload["error"]
        if "EMAIL_USER" in raw_error or "EMAIL_PASS" in raw_error:
            raw_error = "Email credentials not configured"
        return {"status": "error", "error": raw_error, "new_count": 0}

    emails = payload.get("emails") or []
    unread_ids = _unread_ids_from_poll_payload(payload)
    synced_read = _sync_read_status(unread_ids)
    with db.get_db() as conn:
        known = _existing_message_ids(conn)

    new_emails = [e for e in emails if e.get("message_id") and e["message_id"] not in known]
    if not new_emails:
        return {"status": "ok", "new_count": 0, "notified": 0, "synced_read": synced_read}

    classified = await _classify_emails(new_emails)
    by_id = _classification_by_id(classified)
    now = datetime.now(UTC).isoformat()
    notified = 0
    stored: list[dict] = []

    with db.get_db() as conn:
        for em in new_emails:
            mid = em["message_id"]
            meta = by_id.get(mid, {})
            category = meta.get("category", "actionable")
            if category not in ("important", "actionable", "ignorable"):
                category = "actionable"
            importance = float(meta.get("importance", 0.5))
            reason = meta.get("reason", "")

            conn.execute(
                """INSERT INTO inbox_emails
                   (id, sender, subject, preview, received_at, category, importance, reason,
                    notified, digested, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?)""",
                (
                    mid,
                    em.get("from", ""),
                    em.get("subject", ""),
                    em.get("preview", ""),
                    em.get("date") or now,
                    category,
                    importance,
                    reason,
                    now,
                ),
            )
            stored.append({
                "id": mid,
                "category": category,
                "subject": em.get("subject", ""),
                "importance": importance,
                "sender": em.get("from", ""),
            })

    # B2 / C1: emit audit events to event_log (replaces legacy event_recorder)
    for item in stored:
        kwargs: dict = dict(
            payload={
                "sender": item.get("sender", ""),
                "subject": item.get("subject", "")[:200],
                "category": item["category"],
                "importance": item.get("importance", 0.5),
            },
            actor="inbox",
        )
        if execution_id:
            kwargs["caused_by"] = execution_id
        kernel.emit_event("InboxEmailRecorded", "inbox_email", item["id"], **kwargs)

    from app.core.runtime.notification_bridge import push_notification

    for item in stored:
        if item["category"] != "important":
            continue
        title = f"重要邮件 · {item['subject'][:40]}"
        content = f"发件人相关邮件需关注（分类: important，置信度 {item['importance']:.2f}）"
        push_notification("inbox", title, content)
        notified += 1
        with db.get_db() as conn:
            conn.execute("UPDATE inbox_emails SET notified = 1 WHERE id = ?", (item["id"],))

    return {"status": "ok", "new_count": len(stored), "notified": notified, "synced_read": synced_read}


def mark_inbox_email_status(email_id: str, status: str) -> dict | None:
    if status not in ("pending", "read", "handled"):
        raise ValueError(f"Invalid status: {status}")
    with db.get_db() as conn:
        row = conn.execute("SELECT id FROM inbox_emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE inbox_emails SET status = ? WHERE id = ?",
            (status, email_id),
        )
    return {"id": email_id, "status": status}


async def poll_inbox(limit: int = 20, *, execution_id: str | None = None) -> dict:
    """Poll unread inbox via Execution chain (InboxPollRequested → handler)."""
    import uuid

    from app.core.runtime.agent_bootstrap import ensure_scheduler
    from app.core.runtime.agent_scheduler import get_scheduler

    if execution_id:
        cap = await kernel.invoke_capability(
            "check_inbox",
            {"unread_only": True, "limit": max(limit, 50)},
            actor="scheduler",
            execution_id=execution_id,
        )
        if cap.get("status") != "success":
            raw_error = cap.get("error", "check_inbox failed")
            if "EMAIL_USER" in raw_error or "EMAIL_PASS" in raw_error:
                raw_error = "Email credentials not configured"
            return {"status": "error", "error": raw_error, "new_count": 0}
        try:
            payload = json.loads(cap.get("result", "{}"))
        except json.JSONDecodeError:
            return {"status": "error", "error": "invalid inbox JSON", "new_count": 0}
        return await apply_inbox_poll_payload(payload, execution_id=execution_id)

    await ensure_scheduler(kernel)
    scheduler = get_scheduler(kernel)
    await scheduler.start()
    result = await kernel.submit_command(
        "InboxPollRequested",
        "inbox",
        f"inbox_poll_{uuid.uuid4().hex[:8]}",
        payload={"limit": limit},
        actor="scheduler",
        timeout=120.0,
    )
    if result.get("status") == "error":
        return {
            "status": "error",
            "error": result.get("error", "inbox poll failed"),
            "new_count": 0,
        }
    return {
        "status": "ok",
        "new_count": int(result.get("new_count", 0)),
        "notified": int(result.get("notified", 0)),
        "synced_read": int(result.get("synced_read", 0)),
    }


def generate_inbox_digest() -> dict | None:
    """Daily inbox digest — idempotent per calendar day."""
    now = datetime.now(UTC)
    title = f"收件箱摘要 - {now.strftime('%Y-%m-%d')}"

    from app.product.notifications import find_notification

    existing = find_notification("inbox_digest", title)
    if existing:
        return existing

    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT category, sender, subject, reason, importance
               FROM inbox_emails
               WHERE digested = 0 AND COALESCE(status, 'pending') = 'pending'
               ORDER BY importance DESC, created_at DESC
               LIMIT 50"""
        ).fetchall()

    if not rows:
        return None

    grouped: dict[str, list] = {"important": [], "actionable": [], "ignorable": []}
    for row in rows:
        cat = row["category"] if row["category"] in grouped else "actionable"
        grouped[cat].append(dict(row))

    lines = [
        "# 收件箱每日摘要",
        f"日期: {now.strftime('%Y年%m月%d日')}",
        "",
    ]
    labels = {
        "important": "重要",
        "actionable": "待处理",
        "ignorable": "可忽略",
    }
    for cat, label in labels.items():
        items = grouped.get(cat) or []
        if not items:
            continue
        lines.append(f"## {label} ({len(items)})")
        for item in items[:10]:
            lines.append(f"- {item.get('subject', '')} — {item.get('sender', '')}")
            if item.get("reason"):
                lines.append(f"  ({item['reason']})")
        lines.append("")

    content = "\n".join(lines).strip()

    from app.core.runtime.notification_bridge import push_notification

    notif = push_notification("inbox_digest", title, content)

    with db.get_db() as conn:
        conn.execute("UPDATE inbox_emails SET digested = 1 WHERE digested = 0")

    return notif


def list_inbox_emails(
    category: str | None = None,
    limit: int = 50,
    status: str = "pending",
) -> list[dict]:
    with db.get_db() as conn:
        if status == "all":
            if category:
                rows = conn.execute(
                    """SELECT * FROM inbox_emails WHERE category = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inbox_emails ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        elif category:
            rows = conn.execute(
                """SELECT * FROM inbox_emails
                   WHERE category = ? AND COALESCE(status, 'pending') = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (category, status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM inbox_emails
                   WHERE COALESCE(status, 'pending') = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (status, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def latest_digest() -> dict | None:
    from app.core.runtime.kernel_instance import kernel

    rows = kernel.query_state(
        "notifications", type="inbox_digest", limit=1, order="created_at_desc"
    )
    return rows[0] if rows else None
