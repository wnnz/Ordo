import ast
import difflib
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.celery_app import celery
from app.core.config import get_settings
from app.models.entities import Script, ScriptVersion, StoredFile
from app.schemas.common import MessageOut
from app.schemas.script import (
    ScriptCreate,
    ScriptDiffOut,
    ScriptDraftTestIn,
    ScriptFileOut,
    ScriptOut,
    ScriptRestoreIn,
    ScriptTemplateOut,
    ScriptTestTaskOut,
    ScriptUpdate,
    ScriptVersionOut,
    ScriptVersionPage,
)
from app.services.script_templates import list_script_templates
from app.services.script_test_events import (
    cancel_script_test,
    create_script_test,
    get_script_test,
    stream_script_test_events,
)
from app.services.scripts import (
    MAX_SCRIPT_BUNDLE_BYTES,
    MAX_SCRIPT_FILE_BYTES,
    MAX_SCRIPT_FILES,
    entrypoint_file,
    normalize_source_files,
    validate_inputs,
    validate_script,
)
from app.services.storage import object_path
from app.services.workflow_files import (
    contains_file_id,
    create_uploaded_file,
    hydrate_file_references,
    stored_file_available,
)
from app.services.workspaces import audit, require_role, slugify

router = APIRouter(prefix="/workspaces/{workspace_id}/scripts", tags=["scripts"])


async def commit_script(db: DbSession, conflict_message: str = "Script update conflict") -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_message) from exc


async def get_script(
    db: DbSession, workspace_id: str, script_id: str, *, for_update: bool = False
) -> Script:
    if for_update:
        script = await db.scalar(
            select(Script).where(Script.id == script_id).with_for_update()
        )
    else:
        script = await db.get(Script, script_id)
    if not script or script.workspace_id != workspace_id or script.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script not found")
    return script


@router.get("", response_model=list[ScriptOut])
async def list_scripts(
    workspace_id: str, db: DbSession, user: CurrentUser, q: str | None = None
) -> list[Script]:
    await require_role(db, workspace_id, user.id)
    query = select(Script).where(Script.workspace_id == workspace_id, Script.deleted_at.is_(None))
    if q:
        query = query.where(Script.name.ilike(f"%{q}%"))
    return list((await db.scalars(query.order_by(Script.updated_at.desc()))).all())


@router.post("", response_model=ScriptOut, status_code=status.HTTP_201_CREATED)
async def create_script(
    workspace_id: str, payload: ScriptCreate, db: DbSession, user: CurrentUser
) -> Script:
    await require_role(db, workspace_id, user.id, "editor")
    files = normalize_source_files(payload.source_code, payload.source_files)
    digest = validate_script(
        payload.source_code,
        payload.entrypoint,
        payload.input_schema,
        payload.output_schema,
        files,
    )
    slug = payload.slug or slugify(payload.name)
    if await db.scalar(select(Script.id).where(Script.workspace_id == workspace_id, Script.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Script name or slug already exists")
    script = Script(
        workspace_id=workspace_id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        tags=payload.tags,
        latest_version=1,
        created_by=user.id,
    )
    db.add(script)
    await db.flush()
    db.add(
        ScriptVersion(
            workspace_id=workspace_id,
            script_id=script.id,
            version=1,
            source_code=payload.source_code,
            source_files=files,
            entrypoint=payload.entrypoint,
            input_schema=payload.input_schema,
            output_schema=payload.output_schema,
            network_enabled=payload.network_enabled,
            content_hash=digest,
            change_note=payload.change_note,
            created_by=user.id,
        )
    )
    db.add(audit(workspace_id, user.id, "script.created", "script", script.id))
    await commit_script(db, "Script name or slug already exists")
    await db.refresh(script)
    return script


@router.get("/templates", response_model=list[ScriptTemplateOut])
async def script_templates(
    workspace_id: str, db: DbSession, user: CurrentUser
) -> list[dict]:
    await require_role(db, workspace_id, user.id)
    return list_script_templates()


@router.post("/test-files", response_model=ScriptFileOut, status_code=status.HTTP_201_CREATED)
async def upload_script_test_file(
    workspace_id: str,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> StoredFile:
    await require_role(db, workspace_id, user.id, "editor")
    stored = await create_uploaded_file(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        file=file,
        purpose="script_test_input",
    )
    db.add(audit(workspace_id, user.id, "script.test_file_uploaded", "file", stored.id))
    await db.commit()
    await db.refresh(stored)
    return stored


async def build_test_payload(
    db: DbSession,
    workspace_id: str,
    payload: ScriptDraftTestIn,
    script: Script | None = None,
) -> dict:
    version = None
    if script:
        version_number = payload.version or script.latest_version
        version = await db.scalar(
            select(ScriptVersion).where(
                ScriptVersion.script_id == script.id,
                ScriptVersion.version == version_number,
            )
        )
        if not version:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Script version not found")
    has_draft = payload.source_code is not None or bool(payload.source_files)
    if not has_draft and not version:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Draft source is required")
    source = payload.source_code if payload.source_code is not None else (
        version.source_code if version else ""
    )
    source_files = payload.source_files if has_draft else (version.source_files or {"main.py": source})
    entrypoint = payload.entrypoint or (version.entrypoint if version else "main:main")
    input_schema = payload.input_schema if payload.input_schema is not None else (
        version.input_schema if version else {"type": "object"}
    )
    output_schema = payload.output_schema if payload.output_schema is not None else (
        version.output_schema if version else {"type": "object"}
    )
    files = normalize_source_files(source, source_files)
    validate_script(source, entrypoint, input_schema, output_schema, files)
    validate_inputs(input_schema, payload.inputs)
    hydrated_inputs = await hydrate_file_references(db, workspace_id, payload.inputs)
    return {
        "source": source,
        "source_files": files,
        "entrypoint": entrypoint,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "inputs": hydrated_inputs,
        "timeout_seconds": payload.timeout_seconds,
        "memory_mb": payload.memory_mb,
        "network_enabled": (
            payload.network_enabled
            if payload.network_enabled is not None
            else bool(version.network_enabled) if version else False
        ),
    }


async def enqueue_script_test(
    workspace_id: str,
    script_id: str | None,
    task_payload: dict,
    created_by: str,
) -> ScriptTestTaskOut:
    task_id = str(uuid4())
    create_script_test(
        task_id,
        workspace_id,
        script_id,
        {
            **task_payload,
            "__ordo_workspace_id": workspace_id,
            "__ordo_created_by": created_by,
        },
    )
    celery.send_task("script.test", args=[task_id], task_id=task_id)
    return ScriptTestTaskOut(task_id=task_id, status="pending")


@router.post("/test", response_model=ScriptTestTaskOut, status_code=status.HTTP_202_ACCEPTED)
async def test_script_draft(
    workspace_id: str, payload: ScriptDraftTestIn, db: DbSession, user: CurrentUser
) -> ScriptTestTaskOut:
    await require_role(db, workspace_id, user.id, "editor")
    return await enqueue_script_test(
        workspace_id,
        None,
        await build_test_payload(db, workspace_id, payload),
        user.id,
    )


def require_test(workspace_id: str, task_id: str) -> dict:
    task = get_script_test(task_id)
    if not task or task.get("workspace_id") != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script test not found")
    return task


@router.get("/tests/{task_id}/files/{file_id}")
async def download_script_test_file(
    workspace_id: str,
    task_id: str,
    file_id: str,
    db: DbSession,
    user: CurrentUser,
) -> FileResponse:
    await require_role(db, workspace_id, user.id)
    task = require_test(workspace_id, task_id)
    if not contains_file_id(task.get("result") or {}, file_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is not part of this script test")
    stored = await db.get(StoredFile, file_id)
    if (
        not stored
        or stored.workspace_id != workspace_id
        or not stored_file_available(stored)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return FileResponse(
        object_path(stored.object_key),
        media_type=stored.content_type,
        filename=stored.filename,
    )


@router.get("/tests/{task_id}")
async def read_script_test(
    workspace_id: str, task_id: str, db: DbSession, user: CurrentUser
) -> dict:
    await require_role(db, workspace_id, user.id)
    return require_test(workspace_id, task_id)


@router.get("/tests/{task_id}/events")
async def script_test_events(
    workspace_id: str, task_id: str, db: DbSession, user: CurrentUser
) -> StreamingResponse:
    await require_role(db, workspace_id, user.id)
    require_test(workspace_id, task_id)
    return StreamingResponse(
        stream_script_test_events(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/tests/{task_id}/cancel")
async def cancel_script_test_task(
    workspace_id: str, task_id: str, db: DbSession, user: CurrentUser
) -> dict[str, str]:
    await require_role(db, workspace_id, user.id, "editor")
    require_test(workspace_id, task_id)
    cancel_script_test(task_id)
    celery.control.revoke(task_id)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{get_settings().sandbox_url}/executions/{task_id}/cancel",
                headers={"X-Sandbox-Token": get_settings().sandbox_shared_secret},
            )
    except httpx.HTTPError:
        pass
    return {"status": "cancelled"}


@router.post("/upload", response_model=ScriptOut, status_code=status.HTTP_201_CREATED)
async def upload_script(
    workspace_id: str,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
    name: str = Form(...),
    entrypoint: str = Form("main"),
) -> Script:
    await require_role(db, workspace_id, user.id, "editor")
    filename = (file.filename or "").lower()
    if filename.endswith(".py"):
        content = file.file.read(MAX_SCRIPT_FILE_BYTES + 1)
        if len(content) > MAX_SCRIPT_FILE_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Script file too large")
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Script must be UTF-8") from exc
        source_files = {"main.py": source}
        source_type = "python"
    elif filename.endswith(".zip"):
        try:
            archive = zipfile.ZipFile(file.file)
            if len(archive.infolist()) > MAX_SCRIPT_FILES * 4:
                raise ValueError("Archive contains too many entries")
            source_files = {}
            total_size = 0
            python_file_count = 0
            for item in archive.infolist():
                if item.is_dir():
                    continue
                raw_name = item.filename.replace("\\", "/")
                path = PurePosixPath(raw_name)
                mode = item.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or (path.parts and ":" in path.parts[0])
                    or stat.S_ISLNK(mode)
                    or item.flag_bits & 0x1
                ):
                    raise ValueError(f"Unsafe archive entry: {item.filename}")
                if path.suffix.lower() != ".py" or "__MACOSX" in path.parts:
                    continue
                python_file_count += 1
                if python_file_count > MAX_SCRIPT_FILES:
                    raise ValueError("Archive contains too many Python files")
                if item.file_size > MAX_SCRIPT_FILE_BYTES:
                    raise ValueError(f"Script file too large: {item.filename}")
                if item.file_size and (not item.compress_size or item.file_size / item.compress_size > 100):
                    raise ValueError(f"Suspicious compression ratio: {item.filename}")
                total_size += item.file_size
                if total_size > MAX_SCRIPT_BUNDLE_BYTES:
                    raise ValueError("Script bundle too large")
                source_files[str(path)] = archive.read(item).decode("utf-8")
            if not source_files:
                raise ValueError("Archive contains no Python files")
            module, _ = entrypoint_file(entrypoint)
            package_module = module.removesuffix(".py") + "/__init__.py"
            entry_file = module if module in source_files else package_module
            if entry_file not in source_files and entrypoint == "main:main":
                candidates = []
                for candidate_name, candidate_source in source_files.items():
                    tree = ast.parse(candidate_source, filename=candidate_name)
                    if any(
                        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == "main"
                        for node in tree.body
                    ):
                        candidates.append(candidate_name)
                if len(candidates) == 1:
                    entry_file = candidates[0]
                    module_name = entry_file.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".")
                    entrypoint = f"{module_name}:main"
            if entry_file not in source_files:
                raise ValueError(f"Entrypoint module not found: {module}")
            source = source_files[entry_file]
            source_type = "zip"
        except (KeyError, ValueError, SyntaxError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid script archive: {exc}"
            ) from exc
    else:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .py and .zip are supported"
        )
    digest = validate_script(source, entrypoint, {"type": "object"}, {}, source_files)
    script_slug = slugify(name)
    if await db.scalar(
        select(Script.id).where(Script.workspace_id == workspace_id, Script.slug == script_slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Script name or slug already exists")
    script = Script(
        workspace_id=workspace_id,
        name=name,
        slug=script_slug,
        latest_version=1,
        created_by=user.id,
    )
    db.add(script)
    await db.flush()
    db.add(
        ScriptVersion(
            workspace_id=workspace_id,
            script_id=script.id,
            version=1,
            source_type=source_type,
            source_code=source,
            source_files=source_files,
            entrypoint=entrypoint,
            input_schema={"type": "object"},
            output_schema={},
            network_enabled=False,
            content_hash=digest,
            change_note=f"Uploaded {file.filename}",
            created_by=user.id,
        )
    )
    db.add(
        audit(
            workspace_id,
            user.id,
            "script.uploaded",
            "script",
            script.id,
            {"filename": file.filename},
        )
    )
    await commit_script(db, "Script name or slug already exists")
    await db.refresh(script)
    return script


@router.get("/{script_id}", response_model=ScriptOut)
async def read_script(
    workspace_id: str, script_id: str, db: DbSession, user: CurrentUser
) -> Script:
    await require_role(db, workspace_id, user.id)
    return await get_script(db, workspace_id, script_id)


@router.get("/{script_id}/versions", response_model=ScriptVersionPage)
async def list_versions(
    workspace_id: str,
    script_id: str,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ScriptVersionPage:
    await require_role(db, workspace_id, user.id)
    await get_script(db, workspace_id, script_id)
    condition = (
        ScriptVersion.script_id == script_id,
        ScriptVersion.workspace_id == workspace_id,
    )
    total = int(await db.scalar(select(func.count()).select_from(ScriptVersion).where(*condition)) or 0)
    rows = (
        await db.execute(
            select(
                ScriptVersion.id,
                ScriptVersion.script_id,
                ScriptVersion.version,
                ScriptVersion.source_type,
                ScriptVersion.entrypoint,
                ScriptVersion.network_enabled,
                ScriptVersion.content_hash,
                ScriptVersion.change_note,
                ScriptVersion.created_by,
                ScriptVersion.created_at,
            )
            .where(*condition)
            .order_by(ScriptVersion.version.desc())
            .limit(limit)
            .offset(offset)
        )
    ).mappings().all()
    return ScriptVersionPage(items=[dict(row) for row in rows], total=total, limit=limit, offset=offset)


async def get_script_version(
    db: DbSession, workspace_id: str, script_id: str, version_number: int
) -> ScriptVersion:
    version = await db.scalar(
        select(ScriptVersion).where(
            ScriptVersion.workspace_id == workspace_id,
            ScriptVersion.script_id == script_id,
            ScriptVersion.version == version_number,
        )
    )
    if not version:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Script version not found")
    return version


@router.get("/{script_id}/versions/{version_number}", response_model=ScriptVersionOut)
async def read_script_version(
    workspace_id: str,
    script_id: str,
    version_number: int,
    db: DbSession,
    user: CurrentUser,
) -> ScriptVersion:
    await require_role(db, workspace_id, user.id)
    await get_script(db, workspace_id, script_id)
    return await get_script_version(db, workspace_id, script_id, version_number)


def version_bundle_text(version: ScriptVersion) -> list[str]:
    files = version.source_files or {"main.py": version.source_code}
    lines: list[str] = []
    for name in sorted(files):
        lines.extend([f"# file: {name}\n", *files[name].splitlines(keepends=True)])
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
    return lines


@router.get("/{script_id}/diff", response_model=ScriptDiffOut)
async def diff_script_versions(
    workspace_id: str,
    script_id: str,
    db: DbSession,
    user: CurrentUser,
    from_version: int = Query(ge=1),
    to_version: int = Query(ge=1),
) -> ScriptDiffOut:
    await require_role(db, workspace_id, user.id)
    await get_script(db, workspace_id, script_id)
    before = await get_script_version(db, workspace_id, script_id, from_version)
    after = await get_script_version(db, workspace_id, script_id, to_version)
    diff = "".join(
        difflib.unified_diff(
            version_bundle_text(before),
            version_bundle_text(after),
            fromfile=f"version-{from_version}",
            tofile=f"version-{to_version}",
        )
    )
    return ScriptDiffOut(from_version=from_version, to_version=to_version, diff=diff)


@router.post("/{script_id}/restore", response_model=ScriptOut)
async def restore_script_version(
    workspace_id: str,
    script_id: str,
    payload: ScriptRestoreIn,
    db: DbSession,
    user: CurrentUser,
) -> Script:
    await require_role(db, workspace_id, user.id, "editor")
    script = await get_script(db, workspace_id, script_id, for_update=True)
    if script.latest_version != payload.expected_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Script was updated by another member")
    source = await get_script_version(db, workspace_id, script_id, payload.source_version)
    script.latest_version += 1
    db.add(
        ScriptVersion(
            workspace_id=workspace_id,
            script_id=script.id,
            version=script.latest_version,
            source_type=source.source_type,
            source_code=source.source_code,
            source_files=source.source_files,
            entrypoint=source.entrypoint,
            input_schema=source.input_schema,
            output_schema=source.output_schema,
            network_enabled=source.network_enabled,
            content_hash=source.content_hash,
            change_note=payload.change_note,
            created_by=user.id,
        )
    )
    db.add(audit(workspace_id, user.id, "script.version_restored", "script", script.id, {"source_version": payload.source_version, "version": script.latest_version}))
    await db.commit()
    await db.refresh(script)
    return script


@router.put("/{script_id}", response_model=ScriptOut)
async def update_script(
    workspace_id: str, script_id: str, payload: ScriptUpdate, db: DbSession, user: CurrentUser
) -> Script:
    await require_role(db, workspace_id, user.id, "editor")
    script = await get_script(db, workspace_id, script_id, for_update=True)
    if script.latest_version != payload.expected_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Script was updated by another member")
    files = normalize_source_files(payload.source_code, payload.source_files)
    digest = validate_script(
        payload.source_code,
        payload.entrypoint,
        payload.input_schema,
        payload.output_schema,
        files,
    )
    script.latest_version += 1
    if payload.name is not None:
        script.name = payload.name
    if payload.description is not None:
        script.description = payload.description
    if payload.tags is not None:
        script.tags = payload.tags
    db.add(
        ScriptVersion(
            workspace_id=workspace_id,
            script_id=script.id,
            version=script.latest_version,
            source_code=payload.source_code,
            source_files=files,
            entrypoint=payload.entrypoint,
            input_schema=payload.input_schema,
            output_schema=payload.output_schema,
            network_enabled=payload.network_enabled,
            content_hash=digest,
            change_note=payload.change_note,
            created_by=user.id,
        )
    )
    db.add(
        audit(
            workspace_id,
            user.id,
            "script.version_created",
            "script",
            script.id,
            {"version": script.latest_version},
        )
    )
    await db.commit()
    await db.refresh(script)
    return script


@router.post(
    "/{script_id}/test",
    response_model=ScriptTestTaskOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def test_script(
    workspace_id: str,
    script_id: str,
    payload: ScriptDraftTestIn,
    db: DbSession,
    user: CurrentUser,
) -> ScriptTestTaskOut:
    await require_role(db, workspace_id, user.id, "editor")
    script = await get_script(db, workspace_id, script_id)
    return await enqueue_script_test(
        workspace_id,
        script_id,
        await build_test_payload(db, workspace_id, payload, script),
        user.id,
    )


@router.delete("/{script_id}", response_model=MessageOut)
async def delete_script(
    workspace_id: str, script_id: str, db: DbSession, user: CurrentUser
) -> MessageOut:
    await require_role(db, workspace_id, user.id, "editor")
    script = await get_script(db, workspace_id, script_id)
    script.deleted_at = datetime.now(UTC)
    db.add(audit(workspace_id, user.id, "script.deleted", "script", script.id))
    await db.commit()
    return MessageOut(message="Script deleted; referenced versions are retained")
