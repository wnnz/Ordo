from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import uuid4

import redis
from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.entities import WorkflowRun
from app.services.system_settings import runtime_values

ACTIVE_RUN_STATUSES = {"pending", "running", "cancelling"}
RETRYABLE_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
logger = logging.getLogger(__name__)


def new_task_id() -> str:
    return str(uuid4())


def normalize_idempotency_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key:
        return None
    if len(key) > 128 or any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Idempotency-Key must contain 1-128 visible ASCII characters",
        )
    return key


def request_fingerprint(inputs: dict[str, Any], user: str = "") -> str:
    payload = json.dumps(
        {"inputs": inputs, "user": user},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def find_idempotent_run(
    db: AsyncSession,
    *,
    workflow_id: str,
    triggered_by: str,
    idempotency_key: str | None,
    fingerprint: str | None,
) -> WorkflowRun | None:
    if not idempotency_key:
        return None
    run = await db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.triggered_by == triggered_by,
            WorkflowRun.idempotency_key == idempotency_key,
        )
    )
    if run and run.request_fingerprint != fingerprint:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key was already used with a different request",
        )
    return run


async def ensure_public_run_capacity(db: AsyncSession, workflow_id: str) -> None:
    settings = get_settings()
    limit = (await runtime_values()).get(
        "public_max_active_runs_per_app", settings.public_max_active_runs_per_app
    )
    active = await db.scalar(
        select(func.count())
        .select_from(WorkflowRun)
        .where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.triggered_by.in_({"api", "form", "webhook"}),
            WorkflowRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    if int(active or 0) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This application has reached its concurrent run limit",
            headers={"Retry-After": "5"},
        )


@lru_cache
def control_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def cancellation_key(run_id: str) -> str:
    return f"workflow:run:{run_id}:cancel"


def signal_run_cancellation(run_id: str) -> None:
    if get_settings().task_always_eager:
        return
    try:
        control_client().set(cancellation_key(run_id), "1", ex=86_400)
    except redis.RedisError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Run cancellation service is unavailable",
        ) from exc


def run_cancellation_requested(run_id: str) -> bool:
    if get_settings().task_always_eager:
        return False
    try:
        return control_client().get(cancellation_key(run_id)) == "1"
    except redis.RedisError:
        logger.warning(
            "Unable to read workflow cancellation state",
            extra={"run_id": run_id},
            exc_info=True,
        )
        return False


def clear_run_cancellation(run_id: str) -> None:
    if get_settings().task_always_eager:
        return
    try:
        control_client().delete(cancellation_key(run_id))
    except redis.RedisError:
        logger.warning(
            "Unable to clear workflow cancellation state",
            extra={"run_id": run_id},
            exc_info=True,
        )


async def claim_workflow_run(
    db: AsyncSession, run_id: str
) -> tuple[WorkflowRun, str] | None:
    now = datetime.now(UTC)
    settings = get_settings()
    lease_seconds = (await runtime_values()).get(
        "workflow_run_lease_seconds", settings.workflow_run_lease_seconds
    )
    lease_token = str(uuid4())
    result = await db.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == run_id,
            WorkflowRun.status == "pending",
            WorkflowRun.cancel_requested_at.is_(None),
        )
        .values(
            status="running",
            error=None,
            started_at=func.coalesce(WorkflowRun.started_at, now),
            attempt_count=WorkflowRun.attempt_count + 1,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    await db.commit()
    if result.rowcount != 1:
        return None
    run = await db.get(WorkflowRun, run_id)
    return (run, lease_token) if run else None


async def enqueue_persisted_workflow_run(
    db: AsyncSession,
    run: WorkflowRun,
    approval_id: str | None = None,
) -> None:
    from app.services.task_queue import enqueue_workflow_run

    try:
        completed = await enqueue_workflow_run(
            run.id,
            approval_id,
            task_id=run.task_id,
        )
    except Exception as exc:
        await db.refresh(run)
        if run.status == "pending":
            run.status = "failed"
            run.error = "Unable to enqueue workflow run"
            run.finished_at = datetime.now(UTC)
            await db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Workflow queue is unavailable",
        ) from exc
    if completed:
        await db.refresh(run)


async def extend_workflow_run_lease(run_id: str, lease_token: str) -> bool:
    settings = get_settings()
    lease_seconds = (await runtime_values()).get(
        "workflow_run_lease_seconds", settings.workflow_run_lease_seconds
    )
    async with SessionLocal() as db:
        result = await db.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.lease_token == lease_token,
                WorkflowRun.status.in_({"running", "cancelling"}),
            )
            .values(
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds)
            )
        )
        await db.commit()
        return result.rowcount == 1


async def recover_stale_workflow_runs() -> tuple[list[str], list[str]]:
    now = datetime.now(UTC)
    settings = get_settings()
    recovery_seconds = (await runtime_values()).get(
        "workflow_pending_recovery_seconds", settings.workflow_pending_recovery_seconds
    )
    pending_before = now - timedelta(
        seconds=recovery_seconds
    )
    requeue: list[tuple[str, str]] = []
    finished: list[tuple[str, str, str | None]] = []
    async with SessionLocal() as db:
        stale = list(
            (
                await db.scalars(
                    select(WorkflowRun)
                    .where(
                        WorkflowRun.status.in_({"running", "cancelling"}),
                        WorkflowRun.lease_expires_at.is_not(None),
                        WorkflowRun.lease_expires_at < now,
                    )
                    .order_by(WorkflowRun.lease_expires_at)
                    .limit(500)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for run in stale:
            run.status = (
                "cancelled"
                if run.status == "cancelling" or run.cancel_requested_at
                else "failed"
            )
            run.error = None if run.status == "cancelled" else "Workflow worker lease expired"
            run.finished_at = now
            run.lease_token = None
            run.lease_expires_at = None
            finished.append((run.id, run.status, run.error))

        pending = list(
            (
                await db.scalars(
                    select(WorkflowRun)
                    .where(
                        WorkflowRun.status == "pending",
                        WorkflowRun.created_at < pending_before,
                    )
                    .order_by(WorkflowRun.created_at)
                    .limit(500)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for run in pending:
            run.task_id = new_task_id()
            requeue.append((run.id, run.task_id))
        await db.commit()

    from app.services.run_events import publish_run_event
    from app.services.task_queue import enqueue_workflow_run

    for run_id, run_status, run_error in finished:
        publish_run_event(
            run_id,
            {"type": "run_finished", "status": run_status, "error": run_error},
        )
    for run_id, task_id in requeue:
        await enqueue_workflow_run(run_id, task_id=task_id)
    return [item[0] for item in requeue], [item[0] for item in finished]
