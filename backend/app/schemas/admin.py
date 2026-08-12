from datetime import datetime

from pydantic import BaseModel, StrictBool, StrictInt, model_validator


class AdminUserUpdate(BaseModel):
    is_platform_admin: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "AdminUserUpdate":
        if self.is_platform_admin is None and self.is_active is None:
            raise ValueError("At least one user property is required")
        return self


class SystemSettingsUpdate(BaseModel):
    values: dict[str, StrictInt | StrictBool]


class SystemSettingOut(BaseModel):
    key: str
    value: StrictInt | StrictBool
    default: StrictInt | StrictBool
    minimum: int | None = None
    maximum: int | None = None
    unit: str
    type: str
    source: str
    updated_at: datetime | None = None
