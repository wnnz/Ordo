from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.entities import StoredFile
from app.services.document_processing import GeneratedFile
from app.services.storage import object_path, put, remove, storage_root
from app.services.system_settings import runtime_values
from app.services.uploads import store_upload

INTERNAL_FILE_KEY = "__ordo_object_key"
logger = logging.getLogger(__name__)


def _file_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        if value.get("id") and value.get("filename") and value.get("content_type"):
            ids.add(str(value["id"]))
        for item in value.values():
            ids.update(_file_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(_file_ids(item))
    return ids


async def file_expiry(purpose: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    settings = get_settings()
    values = await runtime_values()
    if purpose.endswith("output"):
        return current + timedelta(
            days=values.get("file_output_retention_days", settings.file_output_retention_days)
        )
    return current + timedelta(
        hours=values.get("file_upload_retention_hours", settings.file_upload_retention_hours)
    )


def stored_file_available(stored: StoredFile, now: datetime | None = None) -> bool:
    if stored.expires_at is None:
        return True
    expires_at = stored.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > (now or datetime.now(UTC))


async def create_uploaded_file(
    db: AsyncSession,
    *,
    workspace_id: str,
    created_by: str,
    file: UploadFile,
    purpose: str,
) -> StoredFile:
    key, digest, size = await store_upload(
        workspace_id, file, (await runtime_values()).get("max_upload_bytes", get_settings().max_upload_bytes)
    )
    stored = StoredFile(
        workspace_id=workspace_id,
        object_key=key,
        filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        size=size,
        sha256=digest,
        purpose=purpose,
        expires_at=await file_expiry(purpose),
        created_by=created_by,
    )
    db.add(stored)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        remove(key)
        raise
    return stored


async def extend_file_retention(
    db: AsyncSession,
    workspace_id: str,
    value: Any,
    *,
    purpose: str = "workflow_input",
) -> None:
    ids = _file_ids(value)
    if not ids:
        return
    expires_at = await file_expiry("workflow_output")
    files = list(
        (
            await db.scalars(
                select(StoredFile).where(
                    StoredFile.workspace_id == workspace_id,
                    StoredFile.id.in_(ids),
                )
            )
        ).all()
    )
    for stored in files:
        stored.purpose = purpose
        if stored.expires_at is None or not stored_file_available(stored, expires_at):
            stored.expires_at = expires_at


async def hydrate_file_references(
    db: AsyncSession, workspace_id: str, value: dict[str, Any]
) -> dict[str, Any]:
    ids = _file_ids(value)
    if not ids:
        return value
    files = list(
        (
            await db.scalars(
                select(StoredFile).where(
                    StoredFile.workspace_id == workspace_id,
                    StoredFile.id.in_(ids),
                    or_(StoredFile.expires_at.is_(None), StoredFile.expires_at > datetime.now(UTC)),
                )
            )
        ).all()
    )
    by_id = {item.id: item for item in files}
    if missing := ids - set(by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Uploaded file is missing or belongs to another workspace: {sorted(missing)[0]}",
        )

    def visit(item: Any) -> Any:
        if isinstance(item, dict):
            result = {key: visit(entry) for key, entry in item.items()}
            stored = by_id.get(str(item.get("id") or ""))
            if stored and item.get("filename") and item.get("content_type"):
                result[INTERNAL_FILE_KEY] = stored.object_key
            return result
        if isinstance(item, list):
            return [visit(entry) for entry in item]
        return item

    return visit(value)


def strip_internal_file_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_internal_file_metadata(item)
            for key, item in value.items()
            if not str(key).startswith("__ordo_")
        }
    if isinstance(value, list):
        return [strip_internal_file_metadata(item) for item in value]
    return value


async def materialize_generated_files(
    db: AsyncSession,
    *,
    workspace_id: str,
    created_by: str,
    outputs: dict[str, Any],
    trace: list[dict[str, Any]],
    download_url: Callable[[str], str],
    purpose: str = "workflow_output",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    descriptors: dict[tuple[str, str], dict[str, Any]] = {}

    async def visit(item: Any) -> Any:
        if isinstance(item, GeneratedFile):
            digest = hashlib.sha256(item.content).hexdigest()
            cache_key = (digest, item.filename)
            if cache_key not in descriptors:
                object_key, stored_digest = put(
                    workspace_id,
                    item.filename,
                    item.content_type,
                    item.content,
                )
                stored = StoredFile(
                    workspace_id=workspace_id,
                    object_key=object_key,
                    filename=item.filename,
                    content_type=item.content_type,
                    size=len(item.content),
                    sha256=stored_digest,
                    purpose=purpose,
                    expires_at=await file_expiry(purpose),
                    created_by=created_by,
                )
                db.add(stored)
                try:
                    await db.flush()
                except Exception:
                    remove(object_key)
                    raise
                descriptors[cache_key] = {
                    "id": stored.id,
                    "filename": stored.filename,
                    "content_type": stored.content_type,
                    "size": stored.size,
                    "download_url": download_url(stored.id),
                }
            return descriptors[cache_key]
        if isinstance(item, dict):
            return {
                key: await visit(value)
                for key, value in item.items()
                if not str(key).startswith("__ordo_")
            }
        if isinstance(item, list):
            return [await visit(value) for value in item]
        return item

    materialized = await visit({"outputs": outputs, "trace": trace})
    return materialized["outputs"], materialized["trace"]


def contains_file_id(value: Any, file_id: str) -> bool:
    if isinstance(value, dict):
        if str(value.get("id") or "") == file_id and value.get("download_url"):
            return True
        return any(contains_file_id(item, file_id) for item in value.values())
    if isinstance(value, list):
        return any(contains_file_id(item, file_id) for item in value)
    return False


async def cleanup_file_lifecycle(db: AsyncSession) -> dict[str, int]:
    settings = get_settings()
    values = await runtime_values()
    cleanup_batch_size = values.get("file_cleanup_batch_size", settings.file_cleanup_batch_size)
    now = datetime.now(UTC)
    expired = list(
        (
            await db.scalars(
                select(StoredFile)
                .where(StoredFile.expires_at.is_not(None), StoredFile.expires_at <= now)
                .order_by(StoredFile.expires_at)
                .limit(cleanup_batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    expired_keys = [stored.object_key for stored in expired]
    for stored in expired:
        await db.delete(stored)
    await db.commit()
    for object_key in expired_keys:
        try:
            remove(object_key)
        except OSError:
            logger.warning(
                "Unable to remove expired stored file",
                extra={"object_key": object_key},
                exc_info=True,
            )

    known_keys = set((await db.scalars(select(StoredFile.object_key))).all())
    orphan_cutoff = now - timedelta(
        hours=values.get("file_orphan_grace_hours", settings.file_orphan_grace_hours)
    )
    root = storage_root()
    orphaned = 0
    for path in root.rglob("*"):
        if orphaned >= cleanup_batch_size:
            break
        if not path.is_file():
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            object_key = path.relative_to(root).as_posix()
            if object_key not in known_keys and modified <= orphan_cutoff:
                object_path(object_key).unlink(missing_ok=True)
                orphaned += 1
        except (OSError, ValueError):
            logger.warning(
                "Unable to inspect orphaned stored file",
                extra={"path": str(path)},
                exc_info=True,
            )
    return {"expired": len(expired), "orphaned": orphaned}
