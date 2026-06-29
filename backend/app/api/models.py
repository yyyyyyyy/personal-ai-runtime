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
    """Body for AES-GCM encrypted export.

    Password is sent in the body (not query) so it stays out of access logs,
    shell history, and browser history.
    """

    password: str
    confirm: str = ""


class EncryptedImportRequest(BaseModel):
    """Body for AES-GCM encrypted import.

    Requires the same confirm code as plaintext write import, because the
    underlying path rewrites event_log (drops append-only triggers, clears,
    reinserts) — that is a destructive sovereignty operation.
    """

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

