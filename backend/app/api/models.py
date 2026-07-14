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

    @field_validator("data")
    @classmethod
    def check_size(cls, v: dict) -> dict:
        # Cheap recursive size estimate (avoids a second full json.dumps of
        # near-limit payloads). Counts string/bytes lengths + rough overhead.
        if _approx_payload_bytes(v) > 100 * 1024 * 1024:  # 100MB
            raise ValueError("Import payload too large (max 100MB)")
        return v


def _approx_payload_bytes(obj: object, *, _budget: int = 100 * 1024 * 1024 + 1) -> int:
    """Estimate serialized size without building a full JSON string.

    Stops early once ``_budget`` is exceeded so hostile huge payloads do not
    force a complete walk.
    """
    total = 0
    stack: list[object] = [obj]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            total += 2  # {}
            for k, v in item.items():
                total += len(str(k)) + 3  # key + quotes + colon
                stack.append(v)
                if total > _budget:
                    return total
        elif isinstance(item, (list, tuple)):
            total += 2  # []
            stack.extend(item)
        elif isinstance(item, str):
            total += len(item) + 2
        elif isinstance(item, (bytes, bytearray)):
            total += len(item)
        elif item is None or isinstance(item, bool):
            total += 5
        elif isinstance(item, (int, float)):
            total += 24
        else:
            total += len(str(item)) + 2
        if total > _budget:
            return total
    return total


class DestroyDataRequest(BaseModel):
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


# ── Trigger models ────────────────────────────────────────────────────────


class CreateTriggerRequest(BaseModel):
    name: str
    trigger_type: str = ""
    condition: dict = Field(default_factory=dict)
    action_type: str = "suggestion"
    action_config: dict | None = None


class CreateBackgroundTaskRequest(BaseModel):
    user_request: str
    plan: dict | None = None


class InstallConnectorRequest(BaseModel):
    name: str
    config: dict = Field(default_factory=dict)

