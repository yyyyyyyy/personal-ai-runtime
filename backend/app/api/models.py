"""Pydantic request models for API endpoints."""

from pydantic import BaseModel, Field


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


class CreateMemoryRequest(BaseModel):
    content: str
    category: str | None = None


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    category: str | None = None


class ImportKnowledgeRequest(BaseModel):
    title: str
    content: str


class AskKnowledgeRequest(BaseModel):
    query: str
    n: int = 5
