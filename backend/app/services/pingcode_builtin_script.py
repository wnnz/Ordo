from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Script, ScriptVersion
from app.services.pingcode_worklog_script import (
    PINGCODE_WORKLOG_DESCRIPTION,
    PINGCODE_WORKLOG_INPUT_SCHEMA,
    PINGCODE_WORKLOG_NAME,
    PINGCODE_WORKLOG_OUTPUT_SCHEMA,
    PINGCODE_WORKLOG_SLUG,
    PINGCODE_WORKLOG_SOURCE,
)
from app.services.scripts import validate_script


async def ensure_pingcode_worklog_script(
    db: AsyncSession,
    *,
    workspace_id: str,
    created_by: str,
) -> tuple[Script, bool]:
    script = await db.scalar(
        select(Script).where(
            Script.workspace_id == workspace_id,
            Script.slug == PINGCODE_WORKLOG_SLUG,
        )
    )
    if script and script.deleted_at is None:
        return script, False

    files = {"main.py": PINGCODE_WORKLOG_SOURCE}
    digest = validate_script(
        PINGCODE_WORKLOG_SOURCE,
        "main:main",
        PINGCODE_WORKLOG_INPUT_SCHEMA,
        PINGCODE_WORKLOG_OUTPUT_SCHEMA,
        files,
    )
    if script:
        script.deleted_at = None
        script.name = PINGCODE_WORKLOG_NAME
        script.description = PINGCODE_WORKLOG_DESCRIPTION
        script.tags = ["pingcode", "worklog", "automation"]
        script.latest_version += 1
    else:
        script = Script(
            workspace_id=workspace_id,
            name=PINGCODE_WORKLOG_NAME,
            slug=PINGCODE_WORKLOG_SLUG,
            description=PINGCODE_WORKLOG_DESCRIPTION,
            tags=["pingcode", "worklog", "automation"],
            latest_version=1,
            created_by=created_by,
        )
        db.add(script)
        await db.flush()

    db.add(
        ScriptVersion(
            workspace_id=workspace_id,
            script_id=script.id,
            version=script.latest_version,
            source_code=PINGCODE_WORKLOG_SOURCE,
            source_files=files,
            entrypoint="main:main",
            input_schema=PINGCODE_WORKLOG_INPUT_SCHEMA,
            output_schema=PINGCODE_WORKLOG_OUTPUT_SCHEMA,
            network_enabled=True,
            content_hash=digest,
            change_note="Built-in PingCode worklog filler",
            created_by=created_by,
        )
    )
    return script, True
