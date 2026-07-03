"""Pydantic request models for API endpoints."""

from pydantic import BaseModel, Field, field_validator

MEMORY_CATEGORIES = frozenset({
    "fact", "preference", "habit", "belief", "insight", "work", "personal",
})


class SendMessageRequest(BaseModel):
    content: str


class ResolveApprovalRequest(BaseModel):
    decision: str = "deny"
    tool_name: str = ""
    tool_args: dict = Field(default_factory=dict)
    conv_id: str = ""
    tool_call_id: str = ""


class ExportRequest(BaseModel):
    confirm: str = ""


class ImportRequest(BaseModel):
    data: dict
    read_only: bool = False
    confirm: str = ""


class EncryptedExportRequest(BaseModel):
    password: str
    confirm: str = ""


class EncryptedImportRequest(BaseModel):
    data: str
    password: str
    confirm: str = ""


class CreateMemoryRequest(BaseModel):
    content: str
    category: str | None = None

    @field_validator("category")
    @classmethod
    def check_category(cls, value: str | None) -> str | None:
        if value is not None and value not in MEMORY_CATEGORIES:
            raise ValueError(
                f"category must be one of: {', '.join(sorted(MEMORY_CATEGORIES))}"
            )
        return value


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    category: str | None = None

    @field_validator("category")
    @classmethod
    def check_category(cls, value: str | None) -> str | None:
        if value is not None and value not in MEMORY_CATEGORIES:
            raise ValueError(
                f"category must be one of: {', '.join(sorted(MEMORY_CATEGORIES))}"
            )
        return value


# ── Goal & Action models ──────────────────────────────────────────────────


class CreateGoalRequest(BaseModel):
    title: str
    description: str = ""
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    parent_id: str | None = None
    deadline: str | None = None


class CreateActionRequest(BaseModel):
    title: str
    goal_id: str = ""


# ── Trigger models ────────────────────────────────────────────────────────


class CreateTriggerRequest(BaseModel):
    name: str
    trigger_type: str = ""
    condition: dict = Field(default_factory=dict)
    action_type: str = "suggestion"
    action_config: dict | None = None



class CreateTaskRequest(BaseModel):
    name: str = ""
    title: str = ""
    description: str = ""
    goal_id: str = ""
    parent_goal_id: str | None = None
    parent_task_id: str | None = None
    priority: int = 0
    dependencies: list[str] | None = None


class UpdateTaskStatusRequest(BaseModel):
    status: str
    result: str = ""


class CreateBackgroundTaskRequest(BaseModel):
    user_request: str
    plan: dict | None = None


class InstallConnectorRequest(BaseModel):
    name: str
    config: dict = Field(default_factory=dict)

