from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.api.routes.admin import lock_admin_changes, require_platform_admin
from app.models.entities import SystemSetting
from app.schemas.admin import SystemSettingOut, SystemSettingsUpdate
from app.services.system_settings import invalidate_runtime_values, normalize_values, setting_rows

router = APIRouter(prefix="/admin/settings", tags=["platform administration"])


@router.get("", response_model=list[SystemSettingOut])
async def list_settings(db: DbSession, user: CurrentUser) -> list[dict]:
    require_platform_admin(user)
    return await setting_rows(db)


@router.put("", response_model=list[SystemSettingOut])
async def update_settings(
    payload: SystemSettingsUpdate, db: DbSession, user: CurrentUser
) -> list[dict]:
    require_platform_admin(user)
    try:
        values = normalize_values(payload.values)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    await lock_admin_changes(db)
    defaults = {item["key"]: item["default"] for item in await setting_rows(db)}
    for key, value in values.items():
        row = await db.get(SystemSetting, key)
        if value == defaults[key]:
            if row:
                await db.delete(row)
            continue
        if row:
            row.value = value
            row.updated_by = user.id
        else:
            db.add(SystemSetting(key=key, value=value, updated_by=user.id))
    await db.commit()
    invalidate_runtime_values()
    return await setting_rows(db)
