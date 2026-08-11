from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Script, ScriptVersion
from app.services.scripts import validate_script
from app.services.system_info_script import (
    SYSTEM_INFO_DESCRIPTION,
    SYSTEM_INFO_INPUT_SCHEMA,
    SYSTEM_INFO_NAME,
    SYSTEM_INFO_OUTPUT_SCHEMA,
    SYSTEM_INFO_SLUG,
    SYSTEM_INFO_SOURCE,
)


async def ensure_system_info_script(db: AsyncSession, *, workspace_id: str, created_by: str) -> tuple[Script, bool]:
    script = await db.scalar(select(Script).where(Script.workspace_id == workspace_id, Script.slug == SYSTEM_INFO_SLUG))
    if script and script.deleted_at is None:
        return script, False
    digest = validate_script(SYSTEM_INFO_SOURCE, "main:main", SYSTEM_INFO_INPUT_SCHEMA, SYSTEM_INFO_OUTPUT_SCHEMA, {"main.py": SYSTEM_INFO_SOURCE})
    if script:
        script.deleted_at = None
        script.name = SYSTEM_INFO_NAME
        script.description = SYSTEM_INFO_DESCRIPTION
        script.tags = ["system", "network", "diagnostics"]
        script.latest_version += 1
    else:
        script = Script(workspace_id=workspace_id, name=SYSTEM_INFO_NAME, slug=SYSTEM_INFO_SLUG, description=SYSTEM_INFO_DESCRIPTION, tags=["system", "network", "diagnostics"], latest_version=1, created_by=created_by)
        db.add(script)
        await db.flush()
    db.add(ScriptVersion(workspace_id=workspace_id, script_id=script.id, version=script.latest_version, source_code=SYSTEM_INFO_SOURCE, source_files={"main.py": SYSTEM_INFO_SOURCE}, entrypoint="main:main", input_schema=SYSTEM_INFO_INPUT_SCHEMA, output_schema=SYSTEM_INFO_OUTPUT_SCHEMA, network_enabled=False, content_hash=digest, change_note="Built-in system information collector", created_by=created_by))
    return script, True
