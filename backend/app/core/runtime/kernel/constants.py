"""Constants for the Runtime Kernel — event types, aggregate types, and table names.

Centralising these string literals prevents drift between the Kernel, projectors,
CI checks, and verification scripts.
"""

# ── Event types ─────────────────────────────────────────────────────────────

EVENT_GOAL_CREATED = "GoalCreated"
EVENT_GOAL_UPDATED = "GoalUpdated"
EVENT_GOAL_DELETED = "GoalDeleted"

# ── Task / Action (v0.5.0: unified as WorkItem) ──────────────────────
# DEPRECATED — use WorkItemCreated/Updated/Deleted/StatusChanged instead.
EVENT_TASK_CREATED = "TaskCreated"
EVENT_TASK_STARTED = "TaskStarted"
EVENT_TASK_COMPLETED = "TaskCompleted"
EVENT_TASK_FAILED = "TaskFailed"
EVENT_TASK_STATUS_CHANGED = "TaskStatusChanged"
EVENT_ACTION_CREATED = "ActionCreated"

# ── WorkItem (unified task + action aggregate) ────────────────────────
EVENT_WORK_ITEM_CREATED = "WorkItemCreated"
EVENT_WORK_ITEM_UPDATED = "WorkItemUpdated"
EVENT_WORK_ITEM_DELETED = "WorkItemDeleted"
EVENT_WORK_ITEM_STATUS_CHANGED = "WorkItemStatusChanged"

EVENT_APPROVAL_REQUESTED = "ApprovalRequested"
EVENT_APPROVAL_GRANTED = "ApprovalGranted"
EVENT_APPROVAL_DENIED = "ApprovalDenied"
EVENT_APPROVAL_EXPIRED = "ApprovalExpired"

EVENT_CAPABILITY_INVOKED = "CapabilityInvoked"
EVENT_CAPABILITY_FAILED = "CapabilityFailed"
EVENT_CAPABILITY_DENIED = "CapabilityDenied"
EVENT_CAPABILITY_DEFERRED = "CapabilityDeferred"

EVENT_MEMORY_DERIVED = "MemoryDerived"
EVENT_MEMORY_UPDATED = "MemoryUpdated"
EVENT_MEMORY_DELETED = "MemoryDeleted"

EVENT_CONVERSATION_CREATED = "ConversationCreated"
EVENT_CONVERSATION_UPDATED = "ConversationUpdated"
EVENT_CONVERSATION_DELETED = "ConversationDeleted"
EVENT_MESSAGE_APPENDED = "MessageAppended"

EVENT_ACTION_CREATED = "ActionCreated"

EVENT_NOTIFICATION_CREATED = "NotificationCreated"
EVENT_NOTIFICATION_UPDATED = "NotificationUpdated"
EVENT_NOTIFICATION_READ = "NotificationRead"
EVENT_NOTIFICATION_READ_ALL = "NotificationReadAll"

# ── Chat (ADR Unification) ──────────────────────────────────────────────────

EVENT_CHAT_REQUESTED = "ChatRequested"
EVENT_CHAT_COMPLETED = "ChatCompleted"

EVENT_APPROVE_REQUESTED = "ApproveRequested"
EVENT_APPROVE_COMPLETED = "ApproveCompleted"

EVENT_EXECUTE_REQUESTED = "ExecuteRequested"
EVENT_EXECUTE_COMPLETED = "ExecuteCompleted"

EVENT_BG_TASK_REQUESTED = "BackgroundTaskRequested"
EVENT_BG_TASK_COMPLETED = "BackgroundTaskCompleted"
EVENT_BG_TASK_CREATED = "BackgroundTaskCreated"
EVENT_BG_TASK_STATUS_CHANGED = "BackgroundTaskStatusChanged"
EVENT_BG_TASK_FAILED = "BackgroundTaskFailed"

EVENT_INBOX_POLL_REQUESTED = "InboxPollRequested"
EVENT_INBOX_POLL_COMPLETED = "InboxPollCompleted"
EVENT_INBOX_EMAIL_RECORDED = "InboxEmailRecorded"

EVENT_CHAT_TEXT_DELTA = "ChatTextDelta"   # DELIBERATELY NOT EMITTED TO EVENT_LOG — pushed to SSE queue to avoid polluting Truth Layer
EVENT_CHAT_DONE = "ChatDone"

# ── Application audit ──────────────────────────────────────────

EVENT_APP_CONFIG_CHANGED = "AppConfigChanged"

# ── Execution aggregate (ADR-0007) ──────────────────────────────────────────

EVENT_EXECUTION_REQUESTED = "ExecutionRequested"
EVENT_EXECUTION_STARTED = "ExecutionStarted"
EVENT_EXECUTION_RETRIED = "ExecutionRetried"
EVENT_EXECUTION_PAUSED = "ExecutionPaused"
EVENT_EXECUTION_RESUMED = "ExecutionResumed"
EVENT_EXECUTION_COMPLETED = "ExecutionCompleted"
EVENT_EXECUTION_FAILED = "ExecutionFailed"
EVENT_EXECUTION_CANCELLED = "ExecutionCancelled"

EXECUTION_EVENT_TYPES = frozenset({
    EVENT_EXECUTION_REQUESTED,
    EVENT_EXECUTION_STARTED,
    EVENT_EXECUTION_RETRIED,
    EVENT_EXECUTION_PAUSED,
    EVENT_EXECUTION_RESUMED,
    EVENT_EXECUTION_COMPLETED,
    EVENT_EXECUTION_FAILED,
    EVENT_EXECUTION_CANCELLED,
})

EVENT_USER_PROFILE_UPDATED = "UserProfileUpdated"

# ── Aggregate types ─────────────────────────────────────────────────────────

AGGREGATE_GOAL = "goal"
AGGREGATE_TASK = "task"
AGGREGATE_APPROVAL = "approval"
AGGREGATE_CAPABILITY = "capability"
AGGREGATE_MEMORY = "memory"
AGGREGATE_CONVERSATION = "conversation"
AGGREGATE_ACTION = "action"
AGGREGATE_WORK_ITEM = "work_item"  # v0.5.0: unified task + action aggregate
AGGREGATE_NOTIFICATION = "notification"
AGGREGATE_EXECUTION = "execution"
AGGREGATE_TIMER = "timer"
AGGREGATE_POLICY = "policy"
AGGREGATE_GRANT = "grant"
AGGREGATE_BACKGROUND_TASK = "background_task"
AGGREGATE_INBOX_EMAIL = "inbox_email"

# ── Timer aggregate ─────────────────────────────────────────────────────────

EVENT_TIMER_CREATED = "TimerCreated"
EVENT_TIMER_FIRED = "TimerFired"
EVENT_TIMER_CANCELLED = "TimerCancelled"

# ── Policy aggregate (Governance Event-Sourced) ─────────────────────────────

EVENT_POLICY_CREATED = "PolicyCreated"
EVENT_POLICY_UPDATED = "PolicyUpdated"
EVENT_POLICY_REVOKED = "PolicyRevoked"

# ── Grant aggregate (Governance Event-Sourced) ──────────────────────────────

EVENT_GRANT_CREATED = "GrantCreated"
EVENT_GRANT_REVOKED = "GrantRevoked"

# ── Snapshot-eligible aggregates ─────────────────────────────────────────────

PROJECTION_SNAPSHOT_AGGREGATES = ("goal", "task", "work_item", "memory", "conversation")

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
