"""Constants for the Runtime Kernel — event types, aggregate types, and table names.

Centralising these string literals prevents drift between the Kernel, projectors,
CI checks, and verification scripts.
"""

# ── Event types ─────────────────────────────────────────────────────────────

# ── WorkItem (unified task + action + goal aggregate, v1.0) ──────────
EVENT_WORK_ITEM_CREATED = "WorkItemCreated"
EVENT_WORK_ITEM_UPDATED = "WorkItemUpdated"
EVENT_WORK_ITEM_DELETED = "WorkItemDeleted"
EVENT_WORK_ITEM_STATUS_CHANGED = "WorkItemStatusChanged"

EVENT_APPROVAL_REQUESTED = "ApprovalRequested"
EVENT_APPROVAL_GRANTED = "ApprovalGranted"
EVENT_APPROVAL_DENIED = "ApprovalDenied"  # also covers auto-expired (reason="auto_expired")

EVENT_CAPABILITY_INVOKED = "CapabilityInvoked"
EVENT_CAPABILITY_FAILED = "CapabilityFailed"
EVENT_CAPABILITY_DENIED = "CapabilityDenied"  # also covers deferred (reason="deferred")

EVENT_MEMORY_DERIVED = "MemoryDerived"
EVENT_MEMORY_UPDATED = "MemoryUpdated"
EVENT_MEMORY_DELETED = "MemoryDeleted"
# Emitted when a ChromaDB index repair exhausts its retry budget. The memory
# itself remains authoritative in event_log + memories projection; only the
# derived vector index is missing, so recall silently excludes it.
EVENT_MEMORY_INDEX_REPAIR_FAILED = "MemoryIndexRepairFailed"

EVENT_CONVERSATION_CREATED = "ConversationCreated"
EVENT_CONVERSATION_UPDATED = "ConversationUpdated"
EVENT_CONVERSATION_DELETED = "ConversationDeleted"
EVENT_MESSAGE_APPENDED = "MessageAppended"

EVENT_NOTIFICATION_CREATED = "NotificationCreated"
EVENT_NOTIFICATION_UPDATED = "NotificationUpdated"
EVENT_NOTIFICATION_READ = "NotificationRead"  # aggregate_id="all" marks bulk read

# ── Chat (ADR Unification) ──────────────────────────────────────────────────

EVENT_CHAT_REQUESTED = "ChatRequested"
EVENT_CHAT_COMPLETED = "ChatCompleted"

EVENT_APPROVE_REQUESTED = "ApproveRequested"
EVENT_APPROVE_COMPLETED = "ApproveCompleted"

EVENT_EXECUTE_REQUESTED = "ExecuteRequested"
EVENT_EXECUTE_COMPLETED = "ExecuteCompleted"

EVENT_INBOX_POLL_REQUESTED = "InboxPollRequested"
EVENT_INBOX_POLL_COMPLETED = "InboxPollCompleted"
EVENT_INBOX_EMAIL_RECORDED = "InboxEmailRecorded"
# inbox_emails is a governed projection derived solely from events.
# Status / notified / digested transitions are event-sourced so
# verify_inbox_audit can guarantee the table is fully reconstructable from
# event_log.
EVENT_INBOX_EMAIL_STATUS_CHANGED = "InboxEmailStatusChanged"
# InboxEmailFlagSet covers both notified and digested (payload.flag distinguishes).
EVENT_INBOX_EMAIL_FLAG_SET = "InboxEmailFlagSet"

EVENT_CHAT_TEXT_DELTA = "ChatTextDelta"   # DELIBERATELY NOT EMITTED TO EVENT_LOG — pushed to SSE queue to avoid polluting Truth Layer
EVENT_CHAT_DONE = "ChatDone"

# ── Application audit ──────────────────────────────────────────

EVENT_APP_CONFIG_CHANGED = "AppConfigChanged"
# Telemetry LLM calls are event-sourced. brain_telemetry emits
# this event instead of INSERTing directly into the llm_calls APP_STORAGE
# table. The projector (projectors_governance.py) derives the table row.
EVENT_LLM_CALL_RECORDED = "LLMCallRecorded"

# ── Execution aggregate ──────────────────────────────────────────

EVENT_EXECUTION_REQUESTED = "ExecutionRequested"
EVENT_EXECUTION_STARTED = "ExecutionStarted"
EVENT_EXECUTION_RETRIED = "ExecutionRetried"
EVENT_EXECUTION_COMPLETED = "ExecutionCompleted"
EVENT_EXECUTION_FAILED = "ExecutionFailed"

EXECUTION_EVENT_TYPES = frozenset({
    EVENT_EXECUTION_REQUESTED,
    EVENT_EXECUTION_STARTED,
    EVENT_EXECUTION_RETRIED,
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_FAILED,
})

EVENT_USER_PROFILE_UPDATED = "UserProfileUpdated"

# ── Aggregate types ─────────────────────────────────────────────────────────

AGGREGATE_APPROVAL = "approval"
AGGREGATE_CAPABILITY = "capability"
AGGREGATE_MEMORY = "memory"
AGGREGATE_CONVERSATION = "conversation"
AGGREGATE_WORK_ITEM = "work_item"
AGGREGATE_NOTIFICATION = "notification"
AGGREGATE_EXECUTION = "execution"
AGGREGATE_TIMER = "timer"
AGGREGATE_POLICY = "policy"
AGGREGATE_GRANT = "grant"
AGGREGATE_INBOX_EMAIL = "inbox_email"

# ── Timer aggregate ─────────────────────────────────────────────────────────

EVENT_TIMER_CREATED = "TimerCreated"
EVENT_TIMER_FIRED = "TimerFired"

# ── Policy aggregate (Governance Event-Sourced) ─────────────────────────────

EVENT_POLICY_CREATED = "PolicyCreated"
EVENT_POLICY_UPDATED = "PolicyUpdated"  # also covers revoked (status="revoked")

# ── Snapshot-eligible aggregates ─────────────────────────────────────────────

PROJECTION_SNAPSHOT_AGGREGATES = ("work_item", "memory", "conversation")

# ── Memory index event types ────────────────────────────────────────────────

MEMORY_INDEX_EVENT_TYPES = frozenset({
    EVENT_MEMORY_DERIVED,
    EVENT_MEMORY_UPDATED,
    EVENT_MEMORY_DELETED,
})

# ── Chat bootstrap event types ──────────────────────────────────────────────

CHAT_EVENT_TYPES = frozenset({
    EVENT_CONVERSATION_CREATED,
    EVENT_CONVERSATION_UPDATED,
    EVENT_CONVERSATION_DELETED,
    EVENT_MESSAGE_APPENDED,
})

# ── Event payload schema versions (Architecture Contract) ───────────────────
# Every durable emit stamps ``schema_version`` from this registry.
# Bump an override when that event type's payload *shape* changes in a
# backward-incompatible way; then re-record
# ``scripts/baselines/event_schema_versions.json`` via
# ``python -m scripts.check_event_schema --record``
# (use ``--allow-downgrade`` only for intentional rollback).

PAYLOAD_SCHEMA_VERSION_KEY = "schema_version"
EVENT_SCHEMA_VERSION_DEFAULT = 1

# type string → version. Omit entries that still use the default.
EVENT_SCHEMA_VERSION_OVERRIDES: dict[str, int] = {}


def declared_event_types() -> frozenset[str]:
    """Return all ``EVENT_* = \"...\"`` string values declared in this module."""
    return frozenset(
        v for k, v in globals().items()
        if k.startswith("EVENT_") and isinstance(v, str)
    )


def event_schema_version(event_type: str) -> int:
    """Return the current payload schema version for ``event_type``."""
    return int(
        EVENT_SCHEMA_VERSION_OVERRIDES.get(event_type, EVENT_SCHEMA_VERSION_DEFAULT)
    )


def stamp_event_payload(
    event_type: str,
    payload: dict[str, object] | None,
) -> dict[str, object]:
    """Return a copy of ``payload`` with ``schema_version`` set from the registry."""
    stamped = dict(payload or {})
    stamped[PAYLOAD_SCHEMA_VERSION_KEY] = event_schema_version(event_type)
    return stamped
