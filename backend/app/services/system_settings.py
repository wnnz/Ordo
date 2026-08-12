from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class SystemSettingSpec:
    key: str
    default: Callable[[Settings], int | bool]
    minimum: int | None
    maximum: int | None
    unit: str
    value_type: Literal["integer", "boolean"] = "integer"


SYSTEM_SETTING_SPECS = (
    SystemSettingSpec("max_upload_bytes", lambda settings: settings.max_upload_bytes, 1024, 1024**3, "bytes"),
    SystemSettingSpec("public_rate_limit_requests", lambda settings: settings.public_rate_limit_requests, 0, 100_000, "requests"),
    SystemSettingSpec("public_access_rate_limit_requests", lambda settings: settings.public_access_rate_limit_requests, 0, 100_000, "requests"),
    SystemSettingSpec("public_upload_rate_limit_requests", lambda settings: settings.public_upload_rate_limit_requests, 0, 100_000, "requests"),
    SystemSettingSpec("public_rate_limit_window_seconds", lambda settings: settings.public_rate_limit_window_seconds, 1, 86_400, "seconds"),
    SystemSettingSpec("public_max_active_runs_per_app", lambda settings: settings.public_max_active_runs_per_app, 1, 10_000, "runs"),
    SystemSettingSpec("workflow_run_lease_seconds", lambda settings: settings.workflow_run_lease_seconds, 30, 86_400, "seconds"),
    SystemSettingSpec("workflow_pending_recovery_seconds", lambda settings: settings.workflow_pending_recovery_seconds, 30, 86_400, "seconds"),
    SystemSettingSpec("file_upload_retention_hours", lambda settings: settings.file_upload_retention_hours, 1, 8_760, "hours"),
    SystemSettingSpec("file_output_retention_days", lambda settings: settings.file_output_retention_days, 1, 3_650, "days"),
    SystemSettingSpec("file_orphan_grace_hours", lambda settings: settings.file_orphan_grace_hours, 1, 8_760, "hours"),
    SystemSettingSpec("file_cleanup_batch_size", lambda settings: settings.file_cleanup_batch_size, 1, 10_000, "files"),
    SystemSettingSpec("disable_user_registration", lambda settings: settings.disable_user_registration, None, None, "", "boolean"),
)
SYSTEM_SETTING_BY_KEY = {spec.key: spec for spec in SYSTEM_SETTING_SPECS}

_runtime_cache: dict[str, int | bool] | None = None
_runtime_cache_at = 0.0
RUNTIME_CACHE_SECONDS = 5.0


def default_values() -> dict[str, int | bool]:
    settings = get_settings()
    return {spec.key: spec.default(settings) for spec in SYSTEM_SETTING_SPECS}


def normalize_values(values: dict[str, Any]) -> dict[str, int | bool]:
    normalized: dict[str, int | bool] = {}
    for key, value in values.items():
        spec = SYSTEM_SETTING_BY_KEY.get(key)
        if spec is None:
            raise ValueError(f"Unknown system setting: {key}")
        if spec.value_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"System setting {key} must be a boolean")
            normalized[key] = value
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"System setting {key} must be an integer")
        if value < spec.minimum or value > spec.maximum:
            raise ValueError(
                f"System setting {key} must be between {spec.minimum} and {spec.maximum}"
            )
        normalized[key] = value
    return normalized


async def setting_rows(db) -> list[dict[str, Any]]:
    from app.models.entities import SystemSetting

    defaults = default_values()
    rows = list((await db.scalars(select(SystemSetting))).all())
    overrides = {row.key: row for row in rows if row.key in SYSTEM_SETTING_BY_KEY}
    result = []
    for spec in SYSTEM_SETTING_SPECS:
        row = overrides.get(spec.key)
        value = row.value if row else defaults[spec.key]
        if spec.value_type == "boolean":
            if not isinstance(value, bool):
                value = defaults[spec.key]
        elif isinstance(value, bool) or not isinstance(value, int):
            value = defaults[spec.key]
        normalized = normalize_values({spec.key: value})[spec.key]
        result.append(
            {
                "key": spec.key,
                "value": normalized,
                "default": defaults[spec.key],
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "unit": spec.unit,
                "type": spec.value_type,
                "source": "database" if row else "environment",
                "updated_at": row.updated_at if row else None,
            }
        )
    return result


async def setting_value(db, key: str) -> int | bool:
    from app.models.entities import SystemSetting

    spec = SYSTEM_SETTING_BY_KEY.get(key)
    if spec is None:
        raise KeyError(key)
    row = await db.get(SystemSetting, key)
    value = row.value if row else spec.default(get_settings())
    return normalize_values({key: value})[key]


async def runtime_values(*, force: bool = False) -> dict[str, int | bool]:
    global _runtime_cache, _runtime_cache_at
    now = monotonic()
    if not force and _runtime_cache is not None and now - _runtime_cache_at < RUNTIME_CACHE_SECONDS:
        return dict(_runtime_cache)
    from app.core.database import SessionLocal

    try:
        async with SessionLocal() as db:
            values = {item["key"]: item["value"] for item in await setting_rows(db)}
    except OperationalError as exc:
        # The API can start briefly before Alembic has created the optional
        # override table. Keep environment-backed behavior during that window.
        if "system_settings" not in str(exc).lower():
            raise
        values = {}
    _runtime_cache = values
    _runtime_cache_at = now
    return dict(values)


def invalidate_runtime_values() -> None:
    global _runtime_cache, _runtime_cache_at
    _runtime_cache = None
    _runtime_cache_at = 0.0
