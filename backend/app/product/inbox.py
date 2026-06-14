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
from app.core.telemetry.event_recorder import Event, event_recorder
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

    from app.core.agents.llm_router import llm_router

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


async def poll_inbox(limit: int = 20) -> dict:
    """Poll unread inbox, classify new mail, notify important items."""
    cap = await kernel.invoke_capability(
        "check_inbox",
        {"unread_only": True, "limit": max(limit, 50)},
        actor="scheduler",
    )
    if cap.get("status") != "success":
        return {"status": "error", "error": cap.get("error", "check_inbox failed"), "new_count": 0}

    try:
        payload = json.loads(cap.get("result", "{}"))
    except json.JSONDecodeError:
        return {"status": "error", "error": "invalid inbox JSON", "new_count": 0}

    if payload.get("error"):
        return {"status": "error", "error": payload["error"], "new_count": 0}

    emails = payload.get("emails") or []
    unread_ids = {e["message_id"] for e in emails if e.get("message_id")}
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

    for item in stored:
        event_recorder.record(Event(
            type="email_received",
            summary=f"Email: {item['subject'][:80]}",
            payload={
                "message_id": item["id"],
                "from": item.get("sender", ""),
                "category": item["category"],
            },
        ))

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


def generate_inbox_digest() -> dict | None:
    """Daily inbox digest — idempotent per calendar day."""
    now = datetime.now(UTC)

    with db.get_db() as conn:
        existing = conn.execute(
            "SELECT id, title, content FROM notifications "
            "WHERE type = 'inbox_digest' AND date(created_at) = date('now') LIMIT 1"
        ).fetchone()
        if existing:
            return dict(existing)

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
    title = f"收件箱摘要 - {now.strftime('%Y-%m-%d')}"

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
    with db.get_db() as conn:
        row = conn.execute(
            """SELECT * FROM notifications WHERE type = 'inbox_digest'
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None
