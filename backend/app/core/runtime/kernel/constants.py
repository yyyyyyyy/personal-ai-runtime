"""Constants for the Runtime Kernel — event types, aggregate types, and table names.

Centralising these string literals prevents drift between the Kernel, projectors,
CI checks, and verification scripts.
"""

# ── Event types ─────────────────────────────────────────────────────────────

EVENT_GOAL_CREATED = "GoalCreated"
EVENT_GOAL_UPDATED = "GoalUpdated"
EVENT_GOAL_DELETED = "GoalDeleted"

EVENT_TASK_CREATED = "TaskCreated"
EVENT_TASK_STARTED = "TaskStarted"
EVENT_TASK_COMPLETED = "TaskCompleted"
EVENT_TASK_FAILED = "TaskFailed"
EVENT_TASK_STATUS_CHANGED = "TaskStatusChanged"

EVENT_AGENT_SPAWNED = "AgentSpawned"
EVENT_AGENT_TERMINATED = "AgentTerminated"

EVENT_APPROVAL_REQUESTED = "ApprovalRequested"
EVENT_APPROVAL_GRANTED = "ApprovalGranted"
EVENT_APPROVAL_DENIED = "ApprovalDenied"

EVENT_CAPABILITY_INVOKED = "CapabilityInvoked"
EVENT_CAPABILITY_FAILED = "CapabilityFailed"
EVENT_CAPABILITY_DENIED = "CapabilityDenied"
EVENT_CAPABILITY_DEFERRED = "CapabilityDeferred"

EVENT_MEMORY_DERIVED = "MemoryDerived"
EVENT_MEMORY_UPDATED = "MemoryUpdated"
EVENT_MEMORY_DELETED = "MemoryDeleted"
EVENT_BELIEF_FORMED = "BeliefFormed"

EVENT_CONVERSATION_CREATED = "ConversationCreated"
EVENT_CONVERSATION_UPDATED = "ConversationUpdated"
EVENT_CONVERSATION_DELETED = "ConversationDeleted"
EVENT_MESSAGE_APPENDED = "MessageAppended"

EVENT_ACTION_CREATED = "ActionCreated"
EVENT_ACTION_COMPLETED = "ActionCompleted"

EVENT_PATTERN_RECORDED = "PatternRecorded"

EVENT_FRICTION_LOGGED = "FrictionLogged"
EVENT_FRICTION_RESOLVED = "FrictionResolved"

EVENT_NOTIFICATION_CREATED = "NotificationCreated"
EVENT_NOTIFICATION_UPDATED = "NotificationUpdated"
EVENT_NOTIFICATION_READ = "NotificationRead"
EVENT_NOTIFICATION_READ_ALL = "NotificationReadAll"

EVENT_SCHEDULE_CREATED = "ScheduleCreated"
EVENT_SCHEDULE_LAST_RUN_UPDATED = "ScheduleLastRunUpdated"

EVENT_FEEDBACK_LOGGED = "FeedbackLogged"
EVENT_AGENT_MESSAGE_SENT = "AgentMessageSent"
EVENT_AGENT_MESSAGE_RECEIVED = "AgentMessageReceived"

# ── Aggregate types ─────────────────────────────────────────────────────────

AGGREGATE_GOAL = "goal"
AGGREGATE_TASK = "task"
AGGREGATE_APPROVAL = "approval"
AGGREGATE_CAPABILITY = "capability"
AGGREGATE_MEMORY = "memory"
AGGREGATE_CONVERSATION = "conversation"
AGGREGATE_ACTION = "action"
AGGREGATE_PATTERN = "pattern"
AGGREGATE_FRICTION = "friction"
AGGREGATE_NOTIFICATION = "notification"
AGGREGATE_SCHEDULE = "schedule"

# ── Projection tables ───────────────────────────────────────────────────────

PROJECTION_TABLES = (
    "goals",
    "actions",
    "tasks",
    "memories",
    "approvals",
    "patterns",
    "notifications",
    "schedules",
)

# ── Snapshot-eligible aggregates ─────────────────────────────────────────────

PROJECTION_SNAPSHOT_AGGREGATES = ("goal", "task", "memory", "conversation")

# ── Memory index event types ────────────────────────────────────────────────

MEMORY_INDEX_EVENT_TYPES = frozenset({
    EVENT_MEMORY_DERIVED,
    EVENT_MEMORY_UPDATED,
    EVENT_MEMORY_DELETED,
    EVENT_BELIEF_FORMED,
})

# ── Chat bootstrap event types ──────────────────────────────────────────────

CHAT_EVENT_TYPES = frozenset({
    EVENT_CONVERSATION_CREATED,
    EVENT_CONVERSATION_UPDATED,
    EVENT_CONVERSATION_DELETED,
    EVENT_MESSAGE_APPENDED,
})
