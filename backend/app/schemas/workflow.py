from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ApiModel

WORKFLOW_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=WORKFLOW_SLUG_PATTERN)
    description: str = ""
    app_type: str = "workflow"
    template_id: str | None = Field(default=None, max_length=80)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=80, pattern=WORKFLOW_SLUG_PATTERN)
    graph: dict[str, Any]
    expected_version: int


class WorkflowFolderName(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Folder name cannot be empty")
        return value


class WorkflowFolderCreate(WorkflowFolderName):
    pass


class WorkflowFolderUpdate(WorkflowFolderName):
    pass


class WorkflowFolderOut(ApiModel):
    id: str
    workspace_id: str
    name: str
    workflow_count: int
    created_at: datetime
    updated_at: datetime


class WorkflowFolderMove(BaseModel):
    folder_id: str | None = Field(default=None, max_length=36)


class WorkflowEnvironmentVariableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value_type: str = Field(default="string", pattern="^(string|number|secret)$")
    value: str = Field(default="", max_length=20000)
    description: str = Field(default="", max_length=500)


class WorkflowEnvironmentVariableUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value_type: str = Field(default="string", pattern="^(string|number|secret)$")
    value: str | None = Field(default=None, max_length=20000)
    description: str = Field(default="", max_length=500)


class WorkflowEnvironmentVariableOut(ApiModel):
    id: str
    name: str
    value_type: str
    value: str
    has_value: bool
    description: str
    created_at: datetime
    updated_at: datetime


class WorkflowOut(ApiModel):
    id: str
    workspace_id: str
    folder_id: str | None
    name: str
    slug: str
    description: str
    app_type: str
    draft_graph: dict[str, Any]
    draft_version: int
    published_version_id: str | None
    published_access: str
    created_at: datetime
    updated_at: datetime


class UserAccessGrantIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    expires_at: datetime | None = None


class PasswordAccessGrantIn(BaseModel):
    id: str | None = Field(default=None, max_length=36)
    label: str = Field(default="", max_length=120)
    password: str | None = Field(default=None, min_length=1, max_length=200)
    expires_at: datetime | None = None


class WorkflowAccessGrantOut(ApiModel):
    id: str
    grant_type: str
    user_id: str | None
    label: str
    expires_at: datetime | None
    has_password: bool = False


class PublishIn(BaseModel):
    change_note: str = "Published update"
    access: str = Field(default="public", pattern="^(public|protected)$")
    all_users_enabled: bool = False
    all_users_expires_at: datetime | None = None
    user_grants: list[UserAccessGrantIn] = Field(default_factory=list, max_length=500)
    password_grants: list[PasswordAccessGrantIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_grants(self) -> "PublishIn":
        if self.access == "protected" and not (
            self.all_users_enabled or self.user_grants or self.password_grants
        ):
            raise ValueError("At least one protected access grant is required")
        if len({item.user_id for item in self.user_grants}) != len(self.user_grants):
            raise ValueError("A user can only have one access grant")
        return self


class WorkflowVersionOut(ApiModel):
    id: str
    version: int
    graph: dict[str, Any]
    resolved_references: dict[str, Any]
    change_note: str
    created_at: datetime


class RunIn(BaseModel):
    inputs: dict[str, Any] = {}
    user: str = Field(default="", max_length=255)


class RunOut(ApiModel):
    id: str
    status: str
    triggered_by: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    trace: list[dict[str, Any]]
    error: str | None
    task_id: str | None
    attempt_count: int
    retry_of_run_id: str | None
    started_at: datetime | None
    cancel_requested_at: datetime | None
    created_at: datetime
    finished_at: datetime | None


class RunSummaryOut(ApiModel):
    id: str
    status: str
    triggered_by: str
    error: str | None
    retry_of_run_id: str | None
    started_at: datetime | None
    cancel_requested_at: datetime | None
    created_at: datetime
    finished_at: datetime | None


class RunPage(BaseModel):
    items: list[RunSummaryOut]
    total: int
    limit: int
    offset: int


class ApprovalResponseIn(BaseModel):
    action_id: str = Field(min_length=1, max_length=64)
    data: dict[str, Any] = {}
    comment: str = Field(default="", max_length=4000)


class ApprovalOut(ApiModel):
    id: str
    run_id: str
    node_id: str
    status: str
    request: dict[str, Any]
    response: dict[str, Any]
    expires_at: datetime | None
    created_at: datetime
    responded_at: datetime | None
