from copy import deepcopy
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.security import decrypt_secret, encrypt_secret, hash_password
from app.models.entities import (
    ModelProvider,
    Script,
    ScriptVersion,
    StoredFile,
    Workflow,
    WorkflowAccessGrant,
    WorkflowApproval,
    WorkflowEnvironmentVariable,
    WorkflowFolder,
    WorkflowRun,
    WorkflowVersion,
    WorkspaceMember,
)
from app.schemas.common import ApiModel, MessageOut
from app.schemas.workflow import (
    ApprovalOut,
    ApprovalResponseIn,
    PublishIn,
    RunIn,
    RunOut,
    RunPage,
    RunSummaryOut,
    WorkflowAccessGrantOut,
    WorkflowCreate,
    WorkflowEnvironmentVariableCreate,
    WorkflowEnvironmentVariableOut,
    WorkflowEnvironmentVariableUpdate,
    WorkflowFolderCreate,
    WorkflowFolderMove,
    WorkflowFolderOut,
    WorkflowFolderUpdate,
    WorkflowOut,
    WorkflowUpdate,
    WorkflowVersionOut,
)
from app.services.builtin_scripts import ensure_english_exam_answer_filler_script
from app.services.model_providers import load_model_provider_runtimes
from app.services.pingcode_builtin_script import ensure_pingcode_worklog_script
from app.services.pingcode_worklog_workflow import (
    PINGCODE_ENVIRONMENT_VARIABLES,
    PINGCODE_WORKLOG_WORKFLOW_TEMPLATE_ID,
    build_pingcode_worklog_graph,
)
from app.services.run_control import (
    RETRYABLE_RUN_STATUSES,
    enqueue_persisted_workflow_run,
    new_task_id,
    signal_run_cancellation,
)
from app.services.run_events import publish_run_event, stream_run_events
from app.services.scheduling import next_schedule_at
from app.services.script_runtime import hydrate_script_resources
from app.services.storage import object_path
from app.services.workflow_engine import (
    execute_node_preview,
    resolve_script_references,
    validate_draft_graph,
    validate_graph,
    validate_run_inputs,
)
from app.services.workflow_environment import build_system_variables, load_workflow_environment
from app.services.workflow_files import (
    contains_file_id,
    create_uploaded_file,
    extend_file_retention,
    hydrate_file_references,
    materialize_generated_files,
    stored_file_available,
)
from app.services.workflow_templates import (
    ENGLISH_EXAM_TEMPLATE_ID,
    RDP_DISCONNECT_WORKFLOW_TEMPLATE_ID,
    SYSTEM_INFO_WORKFLOW_TEMPLATE_ID,
    build_chat_graph,
    build_english_exam_graph,
    build_rdp_disconnect_graph,
    build_system_info_graph,
)
from app.services.workspaces import audit, require_role, slugify

router = APIRouter(prefix="/workspaces/{workspace_id}/workflows", tags=["workflows"])

DEFAULT_GRAPH = {
    "schema_version": 1,
    "nodes": [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 80, "y": 160},
            "data": {
                "label": "Start",
                "config": {
                    "triggers": ["form"],
                    "input_fields": [
                        {
                            "name": "message",
                            "label": "Message",
                            "type": "text",
                            "required": False,
                            "placeholder": "",
                            "default_value": "",
                            "max_length": 2000,
                        }
                    ],
                    "schedule": {"cron": "0 9 * * *", "timezone": "UTC", "enabled": False, "inputs_json": "{}"},
                },
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 420, "y": 160},
            "data": {
                "label": "End",
                "config": {
                    "outputs": [
                        {
                            "name": "message",
                            "type": "String",
                            "value": "{{inputs.message}}",
                        }
                    ]
                },
            },
        },
    ],
    "edges": [{"id": "start-end", "source": "start", "target": "end"}],
}


class WorkflowFileOut(ApiModel):
    id: str
    filename: str
    content_type: str
    size: int


async def get_workflow(db: DbSession, workspace_id: str, workflow_id: str) -> Workflow:
    workflow = await db.get(Workflow, workflow_id)
    if not workflow or workflow.workspace_id != workspace_id or workflow.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    return workflow


async def get_workflow_folder(
    db: DbSession, workspace_id: str, folder_id: str
) -> WorkflowFolder:
    folder = await db.get(WorkflowFolder, folder_id)
    if not folder or folder.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow folder not found")
    return folder


def workflow_folder_out(folder: WorkflowFolder, workflow_count: int) -> WorkflowFolderOut:
    return WorkflowFolderOut(
        id=folder.id,
        workspace_id=folder.workspace_id,
        name=folder.name,
        workflow_count=workflow_count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


async def ensure_workflow_slug_available(
    db: DbSession, slug: str, *, workflow_id: str | None = None
) -> None:
    query = select(Workflow.id).where(Workflow.slug == slug)
    if workflow_id:
        query = query.where(Workflow.id != workflow_id)
    if await db.scalar(query):
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow slug is already in use")


async def flush_workflow_slug(db: DbSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow slug is already in use") from exc


async def resolve_subworkflow_references(
    db: DbSession,
    workspace_id: str,
    graph: dict,
    *,
    published: bool,
    ancestors: tuple[str, ...],
) -> tuple[dict, dict[str, dict]]:
    """Embed workspace-scoped child graphs so runs never perform unscoped lookups."""
    resolved_graph = deepcopy(graph)
    references: dict[str, dict] = {}
    for node in resolved_graph.get("nodes", []):
        if node.get("type") != "subworkflow":
            continue
        config = node.setdefault("data", {}).setdefault("config", {})
        target_id = str(config.get("workflow_id") or "")
        if not target_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sub-workflow is required")
        if target_id in ancestors:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sub-workflow cycle detected")
        target = await db.get(Workflow, target_id)
        if not target or target.workspace_id != workspace_id or target.deleted_at is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sub-workflow not found")
        if published:
            version = await db.get(WorkflowVersion, target.published_version_id) if target.published_version_id else None
            if not version or version.workspace_id != workspace_id or version.workflow_id != target.id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Sub-workflow '{target.name}' must be published first",
                )
            child_graph = deepcopy(version.graph)
            reference = {
                "workflow_id": target.id,
                "workflow_name": target.name,
                "workflow_version_id": version.id,
                "version": version.version,
            }
        else:
            child_graph, _ = await resolve_subworkflow_references(
                db,
                workspace_id,
                target.draft_graph,
                published=False,
                ancestors=(*ancestors, target.id),
            )
            reference = {
                "workflow_id": target.id,
                "workflow_name": target.name,
                "draft_version": target.draft_version,
            }
        config["workflow_name"] = target.name
        config["_resolved_graph"] = child_graph
        config["_resolved_reference"] = reference
        references[str(node["id"])] = reference
    return resolved_graph, references


@router.get("/folders", response_model=list[WorkflowFolderOut])
async def list_workflow_folders(
    workspace_id: str, db: DbSession, user: CurrentUser
) -> list[WorkflowFolderOut]:
    await require_role(db, workspace_id, user.id)
    folders = list(
        (
            await db.scalars(
                select(WorkflowFolder)
                .where(WorkflowFolder.workspace_id == workspace_id)
                .order_by(WorkflowFolder.name, WorkflowFolder.id)
            )
        ).all()
    )
    counts = dict(
        (
            await db.execute(
                select(Workflow.folder_id, func.count(Workflow.id))
                .where(
                    Workflow.workspace_id == workspace_id,
                    Workflow.folder_id.is_not(None),
                    Workflow.deleted_at.is_(None),
                )
                .group_by(Workflow.folder_id)
            )
        ).all()
    )
    return [workflow_folder_out(folder, counts.get(folder.id, 0)) for folder in folders]


@router.post("/folders", response_model=WorkflowFolderOut, status_code=status.HTTP_201_CREATED)
async def create_workflow_folder(
    workspace_id: str,
    payload: WorkflowFolderCreate,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowFolderOut:
    await require_role(db, workspace_id, user.id, "editor")
    duplicate = await db.scalar(
        select(WorkflowFolder.id).where(
            WorkflowFolder.workspace_id == workspace_id,
            WorkflowFolder.name == payload.name,
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow folder name already exists")
    folder = WorkflowFolder(workspace_id=workspace_id, name=payload.name, created_by=user.id)
    db.add(folder)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Workflow folder name already exists"
        ) from exc
    db.add(audit(workspace_id, user.id, "workflow_folder.created", "workflow_folder", folder.id))
    await db.commit()
    await db.refresh(folder)
    return workflow_folder_out(folder, 0)


@router.patch("/folders/{folder_id}", response_model=WorkflowFolderOut)
async def update_workflow_folder(
    workspace_id: str,
    folder_id: str,
    payload: WorkflowFolderUpdate,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowFolderOut:
    await require_role(db, workspace_id, user.id, "editor")
    folder = await get_workflow_folder(db, workspace_id, folder_id)
    duplicate = await db.scalar(
        select(WorkflowFolder.id).where(
            WorkflowFolder.workspace_id == workspace_id,
            WorkflowFolder.name == payload.name,
            WorkflowFolder.id != folder_id,
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow folder name already exists")
    previous_name = folder.name
    folder.name = payload.name
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow_folder.updated",
            "workflow_folder",
            folder.id,
            {"name": {"from": previous_name, "to": folder.name}},
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Workflow folder name already exists"
        ) from exc
    await db.refresh(folder)
    workflow_count = await db.scalar(
        select(func.count(Workflow.id)).where(
            Workflow.folder_id == folder.id, Workflow.deleted_at.is_(None)
        )
    )
    return workflow_folder_out(folder, workflow_count or 0)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_folder(
    workspace_id: str, folder_id: str, db: DbSession, user: CurrentUser
) -> None:
    await require_role(db, workspace_id, user.id, "editor")
    folder = await get_workflow_folder(db, workspace_id, folder_id)
    workflow_count = await db.scalar(
        select(func.count(Workflow.id)).where(
            Workflow.folder_id == folder.id, Workflow.deleted_at.is_(None)
        )
    )
    if workflow_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Workflow folder must be empty before deletion"
        )
    db.add(
        audit(workspace_id, user.id, "workflow_folder.deleted", "workflow_folder", folder.id)
    )
    await db.delete(folder)
    await db.commit()


@router.patch("/{workflow_id}/folder", response_model=WorkflowOut)
async def move_workflow_to_folder(
    workspace_id: str,
    workflow_id: str,
    payload: WorkflowFolderMove,
    db: DbSession,
    user: CurrentUser,
) -> Workflow:
    await require_role(db, workspace_id, user.id, "editor")
    workflow = await get_workflow(db, workspace_id, workflow_id)
    if payload.folder_id is not None:
        await get_workflow_folder(db, workspace_id, payload.folder_id)
    previous_folder_id = workflow.folder_id
    workflow.folder_id = payload.folder_id
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow.folder_changed",
            "workflow",
            workflow.id,
            {"folder_id": {"from": previous_folder_id, "to": workflow.folder_id}},
        )
    )
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(workspace_id: str, db: DbSession, user: CurrentUser) -> list[Workflow]:
    await require_role(db, workspace_id, user.id)
    return list(
        (
            await db.scalars(
                select(Workflow)
                .where(Workflow.workspace_id == workspace_id, Workflow.deleted_at.is_(None))
                .order_by(Workflow.updated_at.desc())
            )
        ).all()
    )


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workspace_id: str, payload: WorkflowCreate, db: DbSession, user: CurrentUser
) -> Workflow:
    await require_role(db, workspace_id, user.id, "editor")
    graph = deepcopy(DEFAULT_GRAPH)
    description = payload.description
    app_type = payload.app_type
    install_pingcode_environment = False
    if payload.template_id == ENGLISH_EXAM_TEMPLATE_ID:
        provider = await db.scalar(
            select(ModelProvider)
            .where(ModelProvider.workspace_id == workspace_id)
            .order_by(ModelProvider.created_at, ModelProvider.id)
        )
        if not provider:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Configure a model provider before creating the English exam workflow",
            )
        answer_filler_script, script_created = (
            await ensure_english_exam_answer_filler_script(
                db,
                workspace_id=workspace_id,
                created_by=user.id,
            )
        )
        if script_created:
            db.add(
                audit(
                    workspace_id,
                    user.id,
                    "script.installed",
                    "script",
                    answer_filler_script.id,
                )
            )
        capabilities = provider.config.get("capabilities", {}) if isinstance(provider.config, dict) else {}
        graph = build_english_exam_graph(
            provider_id=provider.id,
            model=provider.default_model,
            vision_enabled=bool(capabilities.get("vision", False)),
            script_id=answer_filler_script.id,
        )
        validate_graph(graph)
        app_type = "workflow"
        description = description or "上传英语试卷 Word 文件，自动完成非听力题并返回红字答案版。"
    elif payload.template_id == PINGCODE_WORKLOG_WORKFLOW_TEMPLATE_ID:
        pingcode_script, script_created = await ensure_pingcode_worklog_script(
            db,
            workspace_id=workspace_id,
            created_by=user.id,
        )
        if script_created:
            db.add(
                audit(
                    workspace_id,
                    user.id,
                    "script.installed",
                    "script",
                    pingcode_script.id,
                )
            )
        graph = build_pingcode_worklog_graph(script_id=pingcode_script.id)
        validate_graph(graph)
        app_type = "workflow"
        install_pingcode_environment = True
        description = description or (
            "按起始年月检查 NEWDMS 迭代，仅为当前用户负责的 Task 补齐法定工作日工时。"
        )
    elif payload.template_id == SYSTEM_INFO_WORKFLOW_TEMPLATE_ID:
        graph = build_system_info_graph()
        validate_graph(graph)
        app_type = "workflow"
        description = description or "通过受保护的 Windows Agent 获取物理机主网卡 IP 和接口信息。"
    elif payload.template_id == RDP_DISCONNECT_WORKFLOW_TEMPLATE_ID:
        graph = build_rdp_disconnect_graph()
        validate_graph(graph)
        app_type = "workflow"
        description = description or (
            "通过本机 Windows Agent 断开当前活跃的远程桌面连接，不注销用户。"
        )
    elif payload.template_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown workflow template")
    elif app_type == "chat":
        provider = await db.scalar(
            select(ModelProvider)
            .where(ModelProvider.workspace_id == workspace_id)
            .order_by(ModelProvider.created_at, ModelProvider.id)
        )
        graph = build_chat_graph(
            provider_id=provider.id if provider else "",
            model=provider.default_model if provider else "",
        )
    workflow_slug = payload.slug or slugify(payload.name)
    await ensure_workflow_slug_available(db, workflow_slug)
    workflow = Workflow(
        workspace_id=workspace_id,
        name=payload.name,
        slug=workflow_slug,
        description=description,
        app_type=app_type,
        draft_graph=graph,
        created_by=user.id,
    )
    db.add(workflow)
    await flush_workflow_slug(db)
    if install_pingcode_environment:
        for name, value_type, variable_description in PINGCODE_ENVIRONMENT_VARIABLES:
            db.add(
                WorkflowEnvironmentVariable(
                    workspace_id=workspace_id,
                    workflow_id=workflow.id,
                    name=name,
                    value_type=value_type,
                    encrypted_value=encrypt_secret(""),
                    description=variable_description,
                    created_by=user.id,
                )
            )
    db.add(audit(workspace_id, user.id, "workflow.created", "workflow", workflow.id))
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def read_workflow(
    workspace_id: str, workflow_id: str, db: DbSession, user: CurrentUser
) -> Workflow:
    await require_role(db, workspace_id, user.id)
    return await get_workflow(db, workspace_id, workflow_id)


@router.get("/{workflow_id}/access-grants", response_model=list[WorkflowAccessGrantOut])
async def list_access_grants(
    workspace_id: str, workflow_id: str, db: DbSession, user: CurrentUser
) -> list[dict]:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    grants = list(
        (
            await db.scalars(
                select(WorkflowAccessGrant)
                .where(WorkflowAccessGrant.workflow_id == workflow_id)
                .order_by(WorkflowAccessGrant.created_at, WorkflowAccessGrant.id)
            )
        ).all()
    )
    return [
        {
            "id": grant.id,
            "grant_type": grant.grant_type,
            "user_id": grant.user_id,
            "label": grant.label,
            "expires_at": grant.expires_at,
            "has_password": bool(grant.password_hash),
        }
        for grant in grants
    ]


def environment_variable_out(variable: WorkflowEnvironmentVariable) -> dict:
    secret = variable.value_type == "secret"
    value = decrypt_secret(variable.encrypted_value)
    return {
        "id": variable.id,
        "name": variable.name,
        "value_type": variable.value_type,
        "value": "••••••••" if secret and value else ("" if secret else value),
        "has_value": bool(value),
        "description": variable.description,
        "created_at": variable.created_at,
        "updated_at": variable.updated_at,
    }


def validate_environment_value(value_type: str, value: str) -> None:
    if value_type == "number":
        try:
            float(value)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Number environment variable requires a numeric value") from exc


@router.get("/{workflow_id}/environment-variables", response_model=list[WorkflowEnvironmentVariableOut])
async def list_environment_variables(workspace_id: str, workflow_id: str, db: DbSession, user: CurrentUser) -> list[dict]:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    variables = list((await db.scalars(select(WorkflowEnvironmentVariable).where(
        WorkflowEnvironmentVariable.workspace_id == workspace_id,
        WorkflowEnvironmentVariable.workflow_id == workflow_id,
    ).order_by(WorkflowEnvironmentVariable.created_at))).all())
    return [environment_variable_out(variable) for variable in variables]


@router.post("/{workflow_id}/environment-variables", response_model=WorkflowEnvironmentVariableOut, status_code=status.HTTP_201_CREATED)
async def create_environment_variable(workspace_id: str, workflow_id: str, payload: WorkflowEnvironmentVariableCreate, db: DbSession, user: CurrentUser) -> dict:
    await require_role(db, workspace_id, user.id, "editor")
    await get_workflow(db, workspace_id, workflow_id)
    if await db.scalar(select(WorkflowEnvironmentVariable.id).where(WorkflowEnvironmentVariable.workflow_id == workflow_id, WorkflowEnvironmentVariable.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Environment variable name already exists")
    validate_environment_value(payload.value_type, payload.value)
    variable = WorkflowEnvironmentVariable(workspace_id=workspace_id, workflow_id=workflow_id, name=payload.name, value_type=payload.value_type, encrypted_value=encrypt_secret(payload.value), description=payload.description, created_by=user.id)
    db.add(variable)
    await db.flush()
    db.add(audit(workspace_id, user.id, "workflow.environment_variable_created", "workflow_environment_variable", variable.id))
    await db.commit()
    await db.refresh(variable)
    return environment_variable_out(variable)


@router.put("/{workflow_id}/environment-variables/{variable_id}", response_model=WorkflowEnvironmentVariableOut)
async def update_environment_variable(workspace_id: str, workflow_id: str, variable_id: str, payload: WorkflowEnvironmentVariableUpdate, db: DbSession, user: CurrentUser) -> dict:
    await require_role(db, workspace_id, user.id, "editor")
    await get_workflow(db, workspace_id, workflow_id)
    variable = await db.scalar(select(WorkflowEnvironmentVariable).where(WorkflowEnvironmentVariable.id == variable_id, WorkflowEnvironmentVariable.workspace_id == workspace_id, WorkflowEnvironmentVariable.workflow_id == workflow_id))
    if not variable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment variable not found")
    duplicate = await db.scalar(select(WorkflowEnvironmentVariable.id).where(WorkflowEnvironmentVariable.workflow_id == workflow_id, WorkflowEnvironmentVariable.name == payload.name, WorkflowEnvironmentVariable.id != variable_id))
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "Environment variable name already exists")
    if payload.value is None and payload.value_type != variable.value_type:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A new value is required when changing variable type")
    if payload.value is not None:
        validate_environment_value(payload.value_type, payload.value)
        variable.encrypted_value = encrypt_secret(payload.value)
    variable.name = payload.name
    variable.value_type = payload.value_type
    variable.description = payload.description
    db.add(audit(workspace_id, user.id, "workflow.environment_variable_updated", "workflow_environment_variable", variable.id))
    await db.commit()
    await db.refresh(variable)
    return environment_variable_out(variable)


@router.delete("/{workflow_id}/environment-variables/{variable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment_variable(workspace_id: str, workflow_id: str, variable_id: str, db: DbSession, user: CurrentUser) -> None:
    await require_role(db, workspace_id, user.id, "editor")
    variable = await db.scalar(select(WorkflowEnvironmentVariable).where(WorkflowEnvironmentVariable.id == variable_id, WorkflowEnvironmentVariable.workspace_id == workspace_id, WorkflowEnvironmentVariable.workflow_id == workflow_id))
    if not variable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Environment variable not found")
    await db.delete(variable)
    db.add(audit(workspace_id, user.id, "workflow.environment_variable_deleted", "workflow_environment_variable", variable_id))
    await db.commit()


@router.post("/{workflow_id}/files", response_model=WorkflowFileOut, status_code=status.HTTP_201_CREATED)
async def upload_workflow_file(
    workspace_id: str,
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> StoredFile:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    stored = await create_uploaded_file(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        file=file,
        purpose="workflow_input",
    )
    db.add(audit(workspace_id, user.id, "workflow.file_uploaded", "file", stored.id))
    await db.commit()
    await db.refresh(stored)
    return stored


@router.put("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workspace_id: str, workflow_id: str, payload: WorkflowUpdate, db: DbSession, user: CurrentUser
) -> Workflow:
    await require_role(db, workspace_id, user.id, "editor")
    workflow = await get_workflow(db, workspace_id, workflow_id)
    if workflow.draft_version != payload.expected_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow was updated by another member")
    validate_draft_graph(payload.graph)
    slug_changed = payload.slug is not None and payload.slug != workflow.slug
    previous_slug = workflow.slug
    if slug_changed:
        await ensure_workflow_slug_available(db, payload.slug, workflow_id=workflow.id)
        workflow.slug = payload.slug
    workflow.draft_graph = payload.graph
    workflow.draft_version += 1
    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if slug_changed:
        await flush_workflow_slug(db)
    detail = {"slug": {"from": previous_slug, "to": workflow.slug}} if slug_changed else None
    db.add(audit(workspace_id, user.id, "workflow.updated", "workflow", workflow.id, detail))
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}", response_model=MessageOut)
async def delete_workflow(
    workspace_id: str, workflow_id: str, db: DbSession, user: CurrentUser
) -> MessageOut:
    await require_role(db, workspace_id, user.id, "editor")
    workflow = await get_workflow(db, workspace_id, workflow_id)
    workflow.deleted_at = datetime.now(UTC)
    workflow.next_run_at = None
    db.add(audit(workspace_id, user.id, "workflow.deleted", "workflow", workflow.id))
    await db.commit()
    return MessageOut(message="Workflow deleted; versions and run history are retained")


@router.post("/{workflow_id}/publish", response_model=WorkflowVersionOut)
async def publish_workflow(
    workspace_id: str, workflow_id: str, payload: PublishIn, db: DbSession, user: CurrentUser
) -> WorkflowVersion:
    await require_role(db, workspace_id, user.id, "editor")
    workflow = await get_workflow(db, workspace_id, workflow_id)
    access_grants: list[WorkflowAccessGrant] = []
    if payload.access == "protected":
        now = datetime.now(UTC)

        def future_expiry(value: datetime | None) -> datetime | None:
            if value and value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            if value and value <= now:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Access grant expiry must be in the future",
                )
            return value

        if payload.all_users_enabled:
            access_grants.append(
                WorkflowAccessGrant(
                    workspace_id=workspace_id,
                    workflow_id=workflow.id,
                    grant_type="all_users",
                    label="All signed-in users",
                    expires_at=future_expiry(payload.all_users_expires_at),
                    created_by=user.id,
                )
            )
        requested_user_ids = [item.user_id for item in payload.user_grants]
        if requested_user_ids:
            member_ids = set(
                await db.scalars(
                    select(WorkspaceMember.user_id).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id.in_(requested_user_ids),
                    )
                )
            )
            if member_ids != set(requested_user_ids):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Selected users must be workspace members",
                )
        for item in payload.user_grants:
            access_grants.append(
                WorkflowAccessGrant(
                    workspace_id=workspace_id,
                    workflow_id=workflow.id,
                    grant_type="user",
                    user_id=item.user_id,
                    expires_at=future_expiry(item.expires_at),
                    created_by=user.id,
                )
            )
        existing_passwords = {
            grant.id: grant.password_hash
            for grant in (
                await db.scalars(
                    select(WorkflowAccessGrant).where(
                        WorkflowAccessGrant.workflow_id == workflow.id,
                        WorkflowAccessGrant.grant_type == "password",
                    )
                )
            ).all()
        }
        for index, item in enumerate(payload.password_grants, start=1):
            password_hash = hash_password(item.password) if item.password else None
            if not password_hash and item.id:
                password_hash = existing_passwords.get(item.id)
            if not password_hash:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Each password grant requires a password of at least 8 characters",
                )
            access_grants.append(
                WorkflowAccessGrant(
                    workspace_id=workspace_id,
                    workflow_id=workflow.id,
                    grant_type="password",
                    label=item.label.strip() or f"Password {index}",
                    password_hash=password_hash,
                    expires_at=future_expiry(item.expires_at),
                    created_by=user.id,
                )
            )
    publish_graph, subworkflow_references = await resolve_subworkflow_references(
        db,
        workspace_id,
        workflow.draft_graph,
        published=True,
        ancestors=(workflow.id,),
    )
    validate_graph(publish_graph)
    scripts = list(
        (
            await db.scalars(
                select(Script).where(
                    Script.workspace_id == workspace_id, Script.deleted_at.is_(None)
                )
            )
        ).all()
    )
    latest: dict[str, tuple[str, int]] = {}
    for script in scripts:
        version = await db.scalar(
            select(ScriptVersion).where(
                ScriptVersion.script_id == script.id, ScriptVersion.version == script.latest_version
            )
        )
        if version:
            latest[script.id] = (version.id, version.version)
    references = resolve_script_references(publish_graph, latest)
    if subworkflow_references:
        references["_subworkflows"] = subworkflow_references
    next_version = (
        await db.scalar(
            select(func.max(WorkflowVersion.version)).where(
                WorkflowVersion.workflow_id == workflow.id
            )
        )
        or 0
    ) + 1
    version = WorkflowVersion(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        version=next_version,
        graph=publish_graph,
        resolved_references=references,
        change_note=payload.change_note,
        created_by=user.id,
    )
    db.add(version)
    await db.flush()
    await db.execute(
        delete(WorkflowAccessGrant).where(WorkflowAccessGrant.workflow_id == workflow.id)
    )
    db.add_all(access_grants)
    workflow.published_version_id = version.id
    workflow.published_access = payload.access
    workflow.next_run_at = next_schedule_at(publish_graph)
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow.published",
            "workflow",
            workflow.id,
            {
                "version": next_version,
                "access": payload.access,
                "access_grants": {
                    "all_users": sum(grant.grant_type == "all_users" for grant in access_grants),
                    "users": sum(grant.grant_type == "user" for grant in access_grants),
                    "passwords": sum(grant.grant_type == "password" for grant in access_grants),
                },
            },
        )
    )
    await db.commit()
    await db.refresh(version)
    return version


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
async def list_versions(
    workspace_id: str, workflow_id: str, db: DbSession, user: CurrentUser
) -> list[WorkflowVersion]:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    return list(
        (
            await db.scalars(
                select(WorkflowVersion)
                .where(WorkflowVersion.workflow_id == workflow_id)
                .order_by(WorkflowVersion.version.desc())
            )
        ).all()
    )


@router.post("/{workflow_id}/versions/{version_id}/restore", response_model=WorkflowOut)
async def restore_version_to_draft(
    workspace_id: str,
    workflow_id: str,
    version_id: str,
    db: DbSession,
    user: CurrentUser,
) -> Workflow:
    await require_role(db, workspace_id, user.id, "editor")
    workflow = await get_workflow(db, workspace_id, workflow_id)
    version = await db.get(WorkflowVersion, version_id)
    if not version or version.workspace_id != workspace_id or version.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow version not found")
    restored_graph = deepcopy(version.graph)
    validate_graph(restored_graph)
    workflow.draft_graph = restored_graph
    workflow.draft_version += 1
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow.version_restored",
            "workflow",
            workflow.id,
            {"version_id": version.id, "version": version.version},
        )
    )
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.post("/{workflow_id}/run", response_model=RunOut)
async def run_draft(
    workspace_id: str, workflow_id: str, payload: RunIn, db: DbSession, user: CurrentUser
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id)
    workflow = await get_workflow(db, workspace_id, workflow_id)
    execution_graph, _ = await resolve_subworkflow_references(
        db,
        workspace_id,
        workflow.draft_graph,
        published=False,
        ancestors=(workflow.id,),
    )
    execution_graph = await hydrate_script_resources(db, execution_graph)
    validate_run_inputs(execution_graph, payload.inputs)
    await extend_file_retention(db, workspace_id, payload.inputs)
    run = WorkflowRun(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        status="pending",
        inputs=payload.inputs,
        execution_graph=execution_graph,
        created_by=user.id,
        task_id=new_task_id(),
    )
    db.add(run)
    await db.flush()
    await db.commit()
    await db.refresh(run)
    await enqueue_persisted_workflow_run(db, run)
    return run


@router.get("/{workflow_id}/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    workspace_id: str,
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
) -> list[WorkflowApproval]:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    return list(
        (
            await db.scalars(
                select(WorkflowApproval)
                .where(
                    WorkflowApproval.workspace_id == workspace_id,
                    WorkflowApproval.workflow_id == workflow_id,
                )
                .order_by(WorkflowApproval.created_at.desc())
                .limit(100)
            )
        ).all()
    )


@router.post(
    "/{workflow_id}/runs/{run_id}/approvals/{approval_id}/respond",
    response_model=RunOut,
)
async def respond_to_approval(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    approval_id: str,
    payload: ApprovalResponseIn,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    run = await db.get(WorkflowRun, run_id)
    approval = await db.get(WorkflowApproval, approval_id)
    if (
        not run
        or run.workspace_id != workspace_id
        or run.workflow_id != workflow_id
        or not approval
        or approval.workspace_id != workspace_id
        or approval.workflow_id != workflow_id
        or approval.run_id != run_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval not found")
    if approval.status != "pending" or run.status != "waiting":
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval is no longer pending")
    now = datetime.now(UTC)
    expires_at = approval.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at and expires_at < now:
        approval.status = "expired"
        run.status = "failed"
        run.error = "Human approval expired"
        run.finished_at = now
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval has expired")
    actions = approval.request.get("actions", [])
    action = next((item for item in actions if str(item.get("id")) == payload.action_id), None)
    if not action:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown approval action")
    response = {
        "action_id": payload.action_id,
        "action_value": action.get("value", payload.action_id),
        "data": payload.data,
        "comment": payload.comment,
        "responded_by": user.id,
    }
    approval.status = "responded"
    approval.response = response
    approval.responded_by = user.id
    approval.responded_at = now
    resume_state = deepcopy(approval.resume_state)
    resume_context = resume_state.setdefault("context", {})
    response_node_id = str(approval.request.get("_response_node_id") or approval.node_id)
    resume_context.setdefault("__human_responses__", {})[response_node_id] = response
    approval.resume_state = resume_state
    run.status = "pending"
    run.error = None
    run.task_id = new_task_id()
    run.cancel_requested_at = None
    run.lease_token = None
    run.lease_expires_at = None
    db.add(audit(workspace_id, user.id, "workflow.approval_responded", "workflow_run", run.id, {"approval_id": approval.id, "action_id": payload.action_id}))
    await db.commit()
    await db.refresh(run)
    await enqueue_persisted_workflow_run(db, run, approval.id)
    return run


@router.post("/{workflow_id}/nodes/{node_id}/run", response_model=RunOut)
async def run_draft_node(
    workspace_id: str,
    workflow_id: str,
    node_id: str,
    payload: RunIn,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id)
    workflow = await get_workflow(db, workspace_id, workflow_id)
    execution_graph, _ = await resolve_subworkflow_references(
        db,
        workspace_id,
        workflow.draft_graph,
        published=False,
        ancestors=(workflow.id,),
    )
    node = next((item for item in execution_graph.get("nodes", []) if item.get("id") == node_id), None)
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow node not found")
    validate_run_inputs(execution_graph, payload.inputs)
    run = WorkflowRun(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        status="running",
        triggered_by="node",
        inputs=payload.inputs,
        created_by=user.id,
        started_at=datetime.now(UTC),
        attempt_count=1,
    )
    db.add(run)
    await db.flush()
    try:
        environment = await load_workflow_environment(db, workspace_id, workflow_id)
        model_providers = await load_model_provider_runtimes(db, workspace_id)
        hydrated_inputs = await hydrate_file_references(db, workspace_id, payload.inputs)
        system = build_system_variables(workflow_id=workflow_id, run_id=run.id, user_id=user.id)
        output, trace = execute_node_preview(
            node,
            hydrated_inputs,
            environment=environment,
            system=system,
            model_providers=model_providers,
        )
        outputs = output if isinstance(output, dict) else {"value": output}
        outputs, traces = await materialize_generated_files(
            db,
            workspace_id=workspace_id,
            created_by=user.id,
            outputs=outputs,
            trace=[trace],
            download_url=lambda file_id: f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs/{run.id}/files/{file_id}",
        )
        run.status = "succeeded"
        run.outputs = outputs
        run.trace = traces
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
    run.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/{workflow_id}/runs", response_model=RunPage)
async def list_runs(
    workspace_id: str,
    workflow_id: str,
    db: DbSession,
    user: CurrentUser,
    limit: int = 20,
    offset: int = 0,
) -> RunPage:
    await require_role(db, workspace_id, user.id)
    await get_workflow(db, workspace_id, workflow_id)
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    filters = (
        WorkflowRun.workspace_id == workspace_id,
        WorkflowRun.workflow_id == workflow_id,
    )
    total = await db.scalar(select(func.count()).select_from(WorkflowRun).where(*filters)) or 0
    rows = (
        await db.execute(
            select(
                WorkflowRun.id,
                WorkflowRun.status,
                WorkflowRun.triggered_by,
                WorkflowRun.error,
                WorkflowRun.retry_of_run_id,
                WorkflowRun.started_at,
                WorkflowRun.cancel_requested_at,
                WorkflowRun.created_at,
                WorkflowRun.finished_at,
            )
            .where(*filters)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).mappings().all()
    items = [RunSummaryOut.model_validate(dict(row)) for row in rows]
    return RunPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/{workflow_id}/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id, "editor")
    run = await db.get(WorkflowRun, run_id)
    if not run or run.workspace_id != workspace_id or run.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    if run.status == "cancelled":
        return run
    if run.status in {"succeeded", "failed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow run has already finished")

    now = datetime.now(UTC)
    if run.status in {"running", "cancelling"}:
        signal_run_cancellation(run.id)
        run.status = "cancelling"
        run.cancel_requested_at = run.cancel_requested_at or now
    else:
        run.status = "cancelled"
        run.cancel_requested_at = now
        run.finished_at = now
        run.lease_token = None
        run.lease_expires_at = None
        await db.execute(
            update(WorkflowApproval)
            .where(
                WorkflowApproval.run_id == run.id,
                WorkflowApproval.status == "pending",
            )
            .values(status="cancelled", responded_at=now)
        )
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow.run_cancelled",
            "workflow_run",
            run.id,
        )
    )
    await db.commit()
    await db.refresh(run)
    if run.status == "cancelled":
        publish_run_event(
            run.id,
            {"type": "run_finished", "status": "cancelled", "error": None},
        )
    else:
        publish_run_event(run.id, {"type": "status", "status": "cancelling"})
    return run


@router.post(
    "/{workflow_id}/runs/{run_id}/retry",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
)
async def retry_run(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id, "editor")
    original = await db.get(WorkflowRun, run_id)
    if (
        not original
        or original.workspace_id != workspace_id
        or original.workflow_id != workflow_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    if original.status not in RETRYABLE_RUN_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only completed or cancelled workflow runs can be retried",
        )
    await extend_file_retention(db, workspace_id, original.inputs)
    run = WorkflowRun(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        workflow_version_id=original.workflow_version_id,
        status="pending",
        triggered_by="retry",
        trigger_user_id=original.trigger_user_id,
        inputs=deepcopy(original.inputs),
        execution_graph=deepcopy(original.execution_graph),
        created_by=user.id,
        retry_of_run_id=original.id,
        task_id=new_task_id(),
    )
    db.add(run)
    await db.flush()
    db.add(
        audit(
            workspace_id,
            user.id,
            "workflow.run_retried",
            "workflow_run",
            run.id,
            {"retry_of_run_id": original.id},
        )
    )
    await db.commit()
    await db.refresh(run)
    await enqueue_persisted_workflow_run(db, run)
    return run


@router.get("/{workflow_id}/runs/{run_id}", response_model=RunOut)
async def get_run(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    db: DbSession,
    user: CurrentUser,
) -> WorkflowRun:
    await require_role(db, workspace_id, user.id)
    run = await db.get(WorkflowRun, run_id)
    if not run or run.workspace_id != workspace_id or run.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    return run


@router.get("/{workflow_id}/runs/{run_id}/files/{file_id}")
async def download_run_file(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    file_id: str,
    db: DbSession,
    user: CurrentUser,
) -> FileResponse:
    await require_role(db, workspace_id, user.id)
    run = await db.get(WorkflowRun, run_id)
    stored = await db.get(StoredFile, file_id)
    if (
        not run
        or run.workspace_id != workspace_id
        or run.workflow_id != workflow_id
        or not stored
        or stored.workspace_id != workspace_id
        or not stored_file_available(stored)
        or not contains_file_id(run.outputs, file_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow output file not found")
    path = object_path(stored.object_key)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow output file not found")
    return FileResponse(path, media_type=stored.content_type, filename=stored.filename)


@router.get("/{workflow_id}/runs/{run_id}/events")
async def get_run_events(
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    db: DbSession,
    user: CurrentUser,
) -> StreamingResponse:
    await require_role(db, workspace_id, user.id)
    run = await db.get(WorkflowRun, run_id)
    if not run or run.workspace_id != workspace_id or run.workflow_id != workflow_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    return StreamingResponse(
        stream_run_events(run.id, run.status),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
