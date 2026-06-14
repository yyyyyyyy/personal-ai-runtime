import json

# --- Conversation projection (chat read models) --------------------------------

from .event import Event
from .projectors_registry import _OWNED_TABLES, projector

_OWNED_TABLES["conversation"] = ["conversations", "messages"]


@projector("ConversationCreated")
def _on_conversation_created(event: Event, conn) -> None:
    p = event.payload
    conn.execute(
        """INSERT OR REPLACE INTO conversations (id, title, summary, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            event.aggregate_id,
            p.get("title", "New Conversation"),
            p.get("summary"),
            p.get("created_at", event.ts),
            event.ts,
        ),
    )


@projector("ConversationUpdated")
def _on_conversation_updated(event: Event, conn) -> None:
    p = event.payload
    fields: list[str] = ["updated_at = ?"]
    params: list[Any] = [event.ts]
    if "title" in p:
        fields.append("title = ?")
        params.append(p["title"])
    if "summary" in p:
        fields.append("summary = ?")
        params.append(p["summary"])
    params.append(event.aggregate_id)
    conn.execute(
        f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?",
        params,
    )


@projector("ConversationDeleted")
def _on_conversation_deleted(event: Event, conn) -> None:
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (event.aggregate_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (event.aggregate_id,))


@projector("MessageAppended")
def _on_message_appended(event: Event, conn) -> None:
    p = event.payload
    msg_id = p.get("message_id") or event.id
    conv_id = event.aggregate_id
    tool_calls = p.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, str):
        tool_calls = json.dumps(tool_calls)
    conn.execute(
        """INSERT OR REPLACE INTO messages
           (id, conversation_id, role, content, tool_calls, tool_call_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            msg_id,
            conv_id,
            p.get("role", "user"),
            p.get("content", ""),
            tool_calls,
            p.get("tool_call_id"),
            p.get("created_at", event.ts),
        ),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (event.ts, conv_id),
    )

