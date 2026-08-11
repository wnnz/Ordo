from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class ScriptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list)
    source_code: str = Field(min_length=1, max_length=1_000_000)
    source_files: dict[str, str] = Field(default_factory=dict)
    entrypoint: str = "main"
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = Field(default_factory=dict)
    network_enabled: bool = False
    change_note: str = "Initial version"


class ScriptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None
    source_code: str = Field(min_length=1, max_length=1_000_000)
    source_files: dict[str, str] = Field(default_factory=dict)
    entrypoint: str = "main"
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = Field(default_factory=dict)
    network_enabled: bool = False
    change_note: str = "Updated script"
    expected_version: int


class ScriptOut(ApiModel):
    id: str
    workspace_id: str
    name: str
    slug: str
    description: str
    tags: list[str]
    latest_version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class ScriptVersionOut(ApiModel):
    id: str
    script_id: str
    version: int
    source_type: str
    source_code: str
    source_files: dict[str, str]
    entrypoint: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    network_enabled: bool
    content_hash: str
    change_note: str
    created_by: str
    created_at: datetime


class ScriptVersionSummaryOut(ApiModel):
    id: str
    script_id: str
    version: int
    source_type: str
    entrypoint: str
    network_enabled: bool
    content_hash: str
    change_note: str
    created_by: str
    created_at: datetime


class ScriptVersionPage(BaseModel):
    items: list[ScriptVersionSummaryOut]
    total: int
    limit: int
    offset: int


class ScriptDraftTestIn(BaseModel):
    version: int | None = None
    source_code: str | None = Field(default=None, max_length=1_000_000)
    source_files: dict[str, str] = Field(default_factory=dict)
    entrypoint: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    memory_mb: int = Field(default=256, ge=64, le=2048)
    network_enabled: bool | None = None


class ScriptTestTaskOut(BaseModel):
    task_id: str
    status: str


class ScriptFileOut(ApiModel):
    id: str
    filename: str
    content_type: str
    size: int


class ScriptRestoreIn(BaseModel):
    source_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    change_note: str = Field(default="Restored version", max_length=1000)


class ScriptDiffOut(BaseModel):
    from_version: int
    to_version: int
    diff: str


class ScriptTemplateOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    source_files: dict[str, str]
    entrypoint: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    sample_inputs: dict[str, Any]
    network_enabled: bool = False


class ScriptTestOut(BaseModel):
    status: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    elapsed_ms: int = 0
    logs_truncated: bool = False
