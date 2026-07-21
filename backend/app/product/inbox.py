"""Proactive Inbox App — poll, classify, notify, daily digest.

Writes only through Kernel.emit_event. The inbox_emails table is a governed
projection derived solely from InboxEmail* events (see projectors_inbox.py).
"""

from __future__ import annotations

import asyncio
import json as _stdlib_json
import logging
import re
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

try:
    import orjson as _orjson

    _json: ModuleType = _orjson
except ImportError:  # pragma: no cover
    _json = _stdlib_json

from app.config import settings
from app.core.runtime import read_ports
from app.core.runtime.kernel import constants
from app.core.runtime.kernel_instance import bind_inbox_poll_applier, kernel

logger = logging.getLogger(__name__)


def _json_dumps_str(data: dict[str, Any]) -> str:
    """Serialize for LLM prompts; always return ``str`` (orjson yields bytes)."""
    raw = _json.dumps(data)
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return raw

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


def _existing_message_ids() -> set[str]:
    rows = read_ports.query_inbox_emails(status="all", limit=5000)
    return {r["id"] for r in rows}


def _format_emails_for_llm(emails: list[dict]) -> str:
    lines = []
    for em in emails:
        # Truncate to save classification tokens.
        subject = em.get("subject", "")
        preview = em.get("preview", "")

        if len(subject) > 100:
            subject = subject[:97] + "..."
        if len(preview) > 200:
            preview = preview[:197] + "..."

        data = {
            "message_id": em.get("message_id", ""),
            "from": em.get("from", ""),
            "subject": subject,
            "preview": preview,
            "date": em.get("date", ""),
        }

        lines.append(_json_dumps_str(data))

    return "\n".join(lines)


async def _classify_emails(emails: list[dict]) -> list[dict]:
    if not emails:
        return []

    from app.core.agents.llm_failover import llm_router
    from app.core.runtime.egress import audit_llm_egress

    client, provider = llm_router.get_client()
    user_prompt = (
        "请分类以下邮件：\n\n"
        f"{_format_emails_for_llm(emails)}\n\n"
        "请以 JSON 格式输出。"
    )

    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    # Route through the egress audit gate for parity with Brain paths.
    # audit_llm_egress emits EgressAudited and returns (messages, audit_meta);
    # we reuse the returned messages so the LLM call matches what was audited.
    audited_messages, _audit = audit_llm_egress(
        messages, purpose="inbox_classify", actor="inbox",
    )

    try:
        response = await client.chat.completions.create(
            model=provider.model,
            messages=audited_messages,
            temperature=0.2,
            max_tokens=settings.llm_max_tokens,
            response_format={"type": "json_object"},
        )  # type: ignore[call-overload]
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
        # Strip potential markdown code blocks that some local models might still add
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        data = _json.loads(cleaned)
        items = data.get("emails", data) if isinstance(data, dict) else data
        if isinstance(items, list) and items:
            return items
    except Exception as e:
        logger.error("Failed to parse classification JSON: %s. Raw: %s", e, raw)

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
    explicit = payload.get("all_unread_emails")
    if explicit is not None:
        return {e["message_id"] for e in explicit if isinstance(e, dict) and e.get("message_id")}

    # Compatibility with old all_unread_message_ids
    legacy = payload.get("all_unread_message_ids")
    if legacy is not None:
        return {mid for mid in legacy if mid}

    emails = payload.get("emails") or []
    return {e["message_id"] for e in emails if e.get("message_id")}


def _sync_unread_status(unread_ids: set[str]) -> int:
    """Synchronize local status with IMAP UNSEEN.

    1. pending -> read: If local is pending but not in UNSEEN.
    2. read -> pending: If local is read but IS in UNSEEN (e.g. mistakenly marked read).
    """
    updated = 0
    # 1. pending -> read
    pending = read_ports.query_pending_inbox_emails(limit=5000)
    for row in pending:
        email_id = row["id"]
        if email_id not in unread_ids:
            kernel.emit_event(
                constants.EVENT_INBOX_EMAIL_STATUS_CHANGED,
                constants.AGGREGATE_INBOX_EMAIL,
                email_id,
                payload={"status": "read"},
                actor="inbox",
            )
            updated += 1

    # 2. read -> pending
    # We only check the most recent 500 "read" emails to avoid massive queries.
    # "handled" is an internal terminal state, we don't sync it back to pending.
    read_emails = read_ports.query_inbox_emails(status="read", limit=500)
    for row in read_emails:
        email_id = row["id"]
        if email_id in unread_ids:
            kernel.emit_event(
                constants.EVENT_INBOX_EMAIL_STATUS_CHANGED,
                constants.AGGREGATE_INBOX_EMAIL,
                email_id,
                payload={"status": "pending"},
                actor="inbox",
            )
            updated += 1
    return updated


async def apply_inbox_poll_payload(payload: dict, *, execution_id: str | None = None) -> dict:
    """Classify new emails, sync read status, store, and notify — shared by poll + handler.

    When *execution_id* is provided (background handler path), InboxEmailRecorded
    events link back to the owning Execution via caused_by.

    Emits InboxEmailRecorded with the full payload; the projection is written
    by projectors_inbox.py inside the Kernel transaction.
    """
    if payload.get("error"):
        raw_error = payload["error"]
        if "EMAIL_USER" in raw_error or "EMAIL_PASS" in raw_error:
            raw_error = "Email credentials not configured"
        return {"status": "error", "error": raw_error, "new_count": 0}

    emails = payload.get("emails") or []
    unread_metadata = payload.get("all_unread_emails") or []
    unread_ids = _unread_ids_from_poll_payload(payload)
    synced_read = _sync_unread_status(unread_ids)
    known = _existing_message_ids()

    # Identify all emails that should be in our DB but aren't
    # 1. Start with the "top" emails (with bodies/previews)
    to_record = {e["message_id"]: e for e in emails if e.get("message_id") and e["message_id"] not in known}

    # 2. Add any other unread emails (from all_unread_emails) if they aren't known
    for ue in unread_metadata:
        mid = ue.get("message_id")
        if mid and mid not in known and mid not in to_record:
            to_record[mid] = ue

    if not to_record:
        return {"status": "ok", "new_count": 0, "notified": 0, "synced_read": synced_read}

    new_emails_list = list(to_record.values())

    CHUNK_SIZE = 20
    classified: list[dict] = []
    if new_emails_list:
        chunks = [
            new_emails_list[i:i + CHUNK_SIZE]
            for i in range(0, len(new_emails_list), CHUNK_SIZE)
        ]
        logger.info(
            "Classifying %d new emails in %d batches",
            len(new_emails_list),
            len(chunks),
        )
        classified_chunks = await asyncio.gather(*(
            _classify_emails(chunk) for chunk in chunks
        ))
        for chunk_result in classified_chunks:
            classified.extend(chunk_result)

    by_id = _classification_by_id(classified)
    now = datetime.now(UTC).isoformat()
    notified = 0
    stored: list[dict] = []

    for mid, em in to_record.items():
        meta = by_id.get(mid, {})
        category = meta.get("category", "actionable")
        if category not in ("important", "actionable", "ignorable"):
            category = "actionable"
        importance = float(meta.get("importance", 0.5))
        reason = meta.get("reason", "")

        kwargs: dict = dict(
            payload={
                "sender": em.get("from", ""),
                "subject": em.get("subject", ""),
                "preview": em.get("preview", ""),
                "received_at": em.get("date") or now,
                "category": category,
                "importance": importance,
                "reason": reason,
                "created_at": now,
            },
            actor="inbox",
        )
        if execution_id:
            kwargs["caused_by"] = execution_id

        kernel.emit_event(
            constants.EVENT_INBOX_EMAIL_RECORDED,
            constants.AGGREGATE_INBOX_EMAIL,
            mid,
            **kwargs,
        )
        stored.append({
            "id": mid,
            "category": category,
            "subject": em.get("subject", ""),
            "importance": importance,
            "sender": em.get("from", ""),
        })

    important_items = [item for item in stored if item["category"] == "important"]

    if len(important_items) == 1:
        item = important_items[0]
        title = f"重要邮件 · {item['subject'][:40]}"
        content = f"发件人 {item['sender']} 相关邮件需关注（置信度 {item['importance']:.2f}）"
        read_ports.push_notification("inbox", title, content)
        notified = 1
    elif len(important_items) > 1:
        title = f"收到 {len(important_items)} 封重要邮件"
        senders = ", ".join(list(dict.fromkeys([item['sender'] for item in important_items]))[:3])
        content = f"来自 {senders} 等发件人的重要邮件已到达，请注意查看。"
        read_ports.push_notification("inbox", title, content)
        notified = len(important_items)

    for item in important_items:
        kernel.emit_event(
            constants.EVENT_INBOX_EMAIL_FLAG_SET,
            constants.AGGREGATE_INBOX_EMAIL,
            item["id"],
            payload={"flag": "notified"},
            actor="inbox",
        )

    return {"status": "ok", "new_count": len(stored), "notified": notified, "synced_read": synced_read}


def _assert_imap_capability_ok(cap_res: dict, *, action: str) -> None:
    """Fail closed when IMAP capability did not succeed."""
    imap_ok = cap_res.get("status") == "success"
    result_raw = cap_res.get("result")
    error = cap_res.get("error")
    if imap_ok and isinstance(result_raw, str):
        try:
            parsed = _json.loads(result_raw)
            if parsed.get("error"):
                imap_ok = False
                error = parsed["error"]
            elif not parsed.get("success", True):
                imap_ok = False
        except Exception:
            pass
    if not imap_ok:
        err = error or "unknown"
        logger.warning("IMAP %s failed: %s", action, err)
        raise ValueError(f"IMAP {action}失败: {err}")


async def mark_inbox_email_status(email_id: str, status: str) -> dict | None:
    if status not in ("pending", "read", "handled"):
        raise ValueError(f"Invalid status: {status}")
    row = read_ports.query_inbox_email(email_id)
    if not row:
        return None

    # Sync to IMAP when state changes. Fail closed so the next poll does not
    # flip local status after a failed IMAP STORE.
    old_status = row.get("status")
    if status != old_status:
        from app.core.runtime.kernel_instance import get_current_execution_id
        execution_id = get_current_execution_id()

        try:
            if status in ("read", "handled") and old_status == "pending":
                cap_res = await kernel.invoke_capability(
                    "mark_inbox_email_read",
                    {"message_id": email_id},
                    actor="user",
                    execution_id=execution_id,
                )
                _assert_imap_capability_ok(cap_res, action="标记已读")
            elif status == "pending" and old_status in ("read", "handled"):
                cap_res = await kernel.invoke_capability(
                    "mark_inbox_email_unread",
                    {"message_id": email_id},
                    actor="user",
                    execution_id=execution_id,
                )
                _assert_imap_capability_ok(cap_res, action="标记未读")
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("Failed to sync status to IMAP for %s: %s", email_id, exc)
            raise ValueError(f"IMAP 同步失败: {exc}") from exc

    kernel.emit_event(
        constants.EVENT_INBOX_EMAIL_STATUS_CHANGED,
        constants.AGGREGATE_INBOX_EMAIL,
        email_id,
        payload={"status": status},
        actor="user",
    )
    return {"id": email_id, "status": status}


async def poll_inbox(limit: int = 20, *, execution_id: str | None = None) -> dict:
    """Poll unread inbox via Execution chain (InboxPollRequested → handler)."""
    import uuid

    from app.core.runtime.kernel_instance import ensure_runtime_scheduler, get_runtime_scheduler

    if execution_id:
        cap = await kernel.invoke_capability(
            "check_inbox",
            {"unread_only": True, "limit": max(limit, 100)},
            actor="scheduler",
            execution_id=execution_id,
        )
        if cap.get("status") != "success":
            raw_error = cap.get("error", "check_inbox failed")
            if "EMAIL_USER" in raw_error or "EMAIL_PASS" in raw_error:
                raw_error = "Email credentials not configured"
            return {"status": "error", "error": raw_error, "new_count": 0}
        try:
            payload = _json.loads(cap.get("result", "{}"))
        except (ValueError, TypeError):
            return {"status": "error", "error": "invalid inbox JSON", "new_count": 0}
        return await apply_inbox_poll_payload(payload, execution_id=execution_id)

    await ensure_runtime_scheduler()
    scheduler = get_runtime_scheduler()
    await scheduler.start()
    result = await kernel.submit_command(
        "InboxPollRequested",
        "inbox",
        f"inbox_poll_{uuid.uuid4().hex[:8]}",
        payload={"limit": limit},
        actor="scheduler",
        timeout=settings.submit_command_timeout_inbox,
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
        return dict(existing)

    rows = read_ports.query_inbox_emails(digested=0, limit=50, order="importance_desc")

    if not rows:
        return None

    grouped: dict[str, list] = {"important": [], "actionable": [], "ignorable": []}
    for row in rows:
        cat = row.get("category") or "actionable"
        if cat not in grouped:
            cat = "actionable"
        grouped[cat].append(row)

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
            reason = item.get("reason")
            if reason:
                lines.append(f"  ({reason})")
        lines.append("")

    content = "\n".join(lines).strip()

    notif = read_ports.push_notification("inbox_digest", title, content)

    kernel.emit_event(
        constants.EVENT_INBOX_EMAIL_FLAG_SET,
        constants.AGGREGATE_INBOX_EMAIL,
        f"digest_{now.strftime('%Y%m%d')}",
        payload={"flag": "digested"},
        actor="inbox",
    )

    return notif


def list_inbox_emails(
    category: str | None = None,
    limit: int = 50,
    status: str = "pending",
) -> list[dict]:
    """Read the inbox_emails projection via read_ports."""
    return read_ports.query_inbox_emails(
        category=category, status=status, limit=limit, order="date_desc",
    )


def latest_digest() -> dict | None:
    rows = read_ports.query_notifications(
        type="inbox_digest", limit=1, order="created_at_desc",
    )
    return rows[0] if rows else None


# Bind Runtime inbox-poll handler → Product applier (R1 inversion).
bind_inbox_poll_applier(apply_inbox_poll_payload)
