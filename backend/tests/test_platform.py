import gc
import io
import os
import shutil
import zipfile
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import sleep as sleep_for_test
from unittest.mock import AsyncMock

TEST_STORAGE_PATH = Path("test-storage").resolve()
TEST_SANDBOX_ARTIFACT_PATH = Path("test-sandbox-artifacts").resolve()
for test_path in (TEST_STORAGE_PATH, TEST_SANDBOX_ARTIFACT_PATH):
    shutil.rmtree(test_path, ignore_errors=True)

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test-ordo.db"
os.environ["TASK_ALWAYS_EAGER"] = "true"
os.environ["STORAGE_PATH"] = str(TEST_STORAGE_PATH)
os.environ["SANDBOX_ARTIFACT_PATH"] = str(TEST_SANDBOX_ARTIFACT_PATH)
os.environ["PUBLIC_RATE_LIMIT_REQUESTS"] = "0"
os.environ["PUBLIC_ACCESS_RATE_LIMIT_REQUESTS"] = "0"
os.environ["PUBLIC_UPLOAD_RATE_LIMIT_REQUESTS"] = "0"
Path("test-ordo.db").unlink(missing_ok=True)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.api.routes.public as public_routes  # noqa: E402
import app.api.routes.workflows as workflow_routes  # noqa: E402
import app.services.workflow_engine as workflow_engine  # noqa: E402
import app.worker as workflow_worker  # noqa: E402
from app.bootstrap import create_schema  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import StoredFile, WorkflowRun  # noqa: E402
from app.services.answer_filling import fill_docx_answers  # noqa: E402
from app.services.run_control import claim_workflow_run  # noqa: E402
from app.services.scripts import validate_script  # noqa: E402
from app.services.workflow_engine import (  # noqa: E402
    execute_graph,
    execute_http_request,
    execute_node,
    validate_answer_filler_config,
    validate_code_config,
    validate_document_config,
    validate_http_config,
    validate_llm_config,
)
from app.services.workflow_files import cleanup_file_lifecycle  # noqa: E402


@pytest.mark.asyncio
async def test_create_schema_retries_until_database_is_ready(monkeypatch):
    import app.bootstrap as bootstrap

    class Connection:
        run_sync = AsyncMock()

    class BeginContext:
        async def __aenter__(self):
            fake_engine.attempts += 1
            if fake_engine.attempts < 3:
                raise ConnectionError("database is starting up")
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class Engine:
        attempts = 0

        def begin(self):
            return BeginContext()

    fake_engine = Engine()
    sleep = AsyncMock()
    monkeypatch.setattr(bootstrap, "engine", fake_engine)
    monkeypatch.setattr(bootstrap.asyncio, "sleep", sleep)

    await bootstrap.create_schema(max_attempts=3, retry_delay_seconds=0.01)

    assert fake_engine.attempts == 3
    assert sleep.await_count == 2


def test_development_encryption_key_derives_invalid_config_but_production_rejects(monkeypatch):
    import app.core.security as security

    class DevelopmentSettings:
        credential_encryption_key = "development-placeholder"
        app_secret_key = "unused"
        app_env = "development"

    monkeypatch.setattr(security, "get_settings", lambda: DevelopmentSettings())
    encrypted = security.encrypt_secret("secret-value")
    assert security.decrypt_secret(encrypted) == "secret-value"

    class ProductionSettings(DevelopmentSettings):
        app_env = "production"

    monkeypatch.setattr(security, "get_settings", lambda: ProductionSettings())
    with pytest.raises(RuntimeError, match="valid Fernet key"):
        security.encrypt_secret("secret-value")


@pytest.fixture(scope="module", autouse=True)
def schema():
    import asyncio

    asyncio.run(create_schema())
    yield
    asyncio.run(engine.dispose())
    gc.collect()
    for _ in range(20):
        try:
            Path("test-ordo.db").unlink(missing_ok=True)
            break
        except PermissionError:
            sleep_for_test(0.05)
    for test_path in (TEST_STORAGE_PATH, TEST_SANDBOX_ARTIFACT_PATH):
        shutil.rmtree(test_path, ignore_errors=True)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def register(client: TestClient, email: str, name: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "display_name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_multi_workspace_invitation_and_role_boundary(client: TestClient):
    owner = register(client, "owner@example.com", "Owner")
    member = register(client, "member@example.com", "Member")
    assert owner["user"]["is_platform_admin"] is True
    assert member["user"]["is_platform_admin"] is False
    assert owner["user"]["is_active"] is True
    assert member["user"]["is_active"] is True
    users = client.get("/api/v1/admin/users", headers=auth(owner))
    assert users.status_code == 200
    assert client.get("/api/v1/admin/users", headers=auth(member)).status_code == 403
    promoted = client.patch(
        f"/api/v1/admin/users/{member['user']['id']}",
        headers=auth(owner),
        json={"is_platform_admin": True},
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_platform_admin"] is True
    assert client.get("/api/v1/admin/users", headers=auth(member)).status_code == 200
    disabled = client.patch(
        f"/api/v1/admin/users/{member['user']['id']}",
        headers=auth(owner),
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "correct-horse-battery"},
    ).status_code == 403
    assert client.get("/api/v1/auth/me", headers=auth(member)).status_code == 401
    enabled = client.patch(
        f"/api/v1/admin/users/{member['user']['id']}",
        headers=auth(owner),
        json={"is_active": True},
    )
    assert enabled.status_code == 200

    workspaces = client.get("/api/v1/workspaces", headers=auth(owner)).json()
    assert len(workspaces) == 1
    workspace_id = workspaces[0]["id"]
    created = client.post(
        "/api/v1/workspaces",
        headers=auth(owner),
        json={"name": "Shared AI Lab", "timezone": "Asia/Singapore"},
    )
    assert created.status_code == 201

    invitation = client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=auth(owner),
        json={"email": "member@example.com", "role": "editor", "max_uses": 1},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        f"/api/v1/workspaces/invitations/{invitation.json()['token']}/accept",
        headers=auth(member),
    )
    assert accepted.status_code == 200
    member_workspaces = client.get("/api/v1/workspaces", headers=auth(member)).json()
    assert any(item["id"] == workspace_id and item["role"] == "editor" for item in member_workspaces)


def test_platform_system_settings_are_admin_only_and_persist(client: TestClient):
    admin = register(client, "system-settings-admin@example.com", "System Settings Admin")
    member = register(client, "system-settings-member@example.com", "System Settings Member")
    if not admin["user"]["is_platform_admin"]:
        bootstrap = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "correct-horse-battery"},
        )
        assert bootstrap.status_code == 200, bootstrap.text
        promoted = client.patch(
            f"/api/v1/admin/users/{admin['user']['id']}",
            headers=auth(bootstrap.json()),
            json={"is_platform_admin": True},
        )
        assert promoted.status_code == 200, promoted.text

    assert client.get("/api/v1/admin/settings").status_code == 401
    assert client.get("/api/v1/admin/settings", headers=auth(member)).status_code == 403

    initial = client.get("/api/v1/admin/settings", headers=auth(admin))
    assert initial.status_code == 200, initial.text
    settings = {item["key"]: item for item in initial.json()}
    assert settings["public_max_active_runs_per_app"]["source"] == "environment"

    updated = client.put(
        "/api/v1/admin/settings",
        headers=auth(admin),
        json={"values": {"public_max_active_runs_per_app": 17}},
    )
    assert updated.status_code == 200, updated.text
    changed = {item["key"]: item for item in updated.json()}["public_max_active_runs_per_app"]
    assert changed["value"] == 17
    assert changed["source"] == "database"

    restored = client.put(
        "/api/v1/admin/settings",
        headers=auth(admin),
        json={"values": {"public_max_active_runs_per_app": changed["default"]}},
    )
    assert restored.status_code == 200, restored.text
    reset = {item["key"]: item for item in restored.json()}["public_max_active_runs_per_app"]
    assert reset["source"] == "environment"

    disabled = client.put(
        "/api/v1/admin/settings",
        headers=auth(admin),
        json={"values": {"disable_user_registration": True}},
    )
    assert disabled.status_code == 200, disabled.text
    registration_setting = {
        item["key"]: item for item in disabled.json()
    }["disable_user_registration"]
    assert registration_setting["value"] is True
    assert registration_setting["type"] == "boolean"
    blocked = client.post(
        "/api/v1/auth/register",
        json={
            "email": "registration-disabled@example.com",
            "password": "correct-horse-battery",
            "display_name": "Registration Disabled",
        },
    )
    assert blocked.status_code == 403, blocked.text

    enabled = client.put(
        "/api/v1/admin/settings",
        headers=auth(admin),
        json={"values": {"disable_user_registration": False}},
    )
    assert enabled.status_code == 200, enabled.text
    reopened = client.post(
        "/api/v1/auth/register",
        json={
            "email": "registration-reopened@example.com",
            "password": "correct-horse-battery",
            "display_name": "Registration Reopened",
        },
    )
    assert reopened.status_code == 201, reopened.text


def test_workflow_slug_is_editable_validated_and_globally_unique(client: TestClient):
    session = register(client, "slug-owner@example.com", "Slug Owner")
    headers = auth(session)
    first_workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Slug Workspace One", "timezone": "Asia/Singapore"},
    ).json()
    second_workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Slug Workspace Two", "timezone": "Asia/Singapore"},
    ).json()

    invalid = client.post(
        f"/api/v1/workspaces/{first_workspace['id']}/workflows",
        headers=headers,
        json={"name": "Invalid slug", "slug": "Invalid Slug"},
    )
    assert invalid.status_code == 422

    created = client.post(
        f"/api/v1/workspaces/{first_workspace['id']}/workflows",
        headers=headers,
        json={"name": "English answer filler", "slug": "english-answer-filler"},
    )
    assert created.status_code == 201, created.text
    workflow = created.json()
    published = client.post(
        f"/api/v1/workspaces/{first_workspace['id']}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"change_note": "Initial slug release"},
    )
    assert published.status_code == 200, published.text
    assert client.get("/v1/apps/english-answer-filler").status_code == 200

    duplicate = client.post(
        f"/api/v1/workspaces/{second_workspace['id']}/workflows",
        headers=headers,
        json={"name": "Duplicate", "slug": "english-answer-filler"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Workflow slug is already in use"

    other = client.post(
        f"/api/v1/workspaces/{second_workspace['id']}/workflows",
        headers=headers,
        json={"name": "Other", "slug": "other-workflow-address"},
    ).json()
    conflict = client.put(
        f"/api/v1/workspaces/{second_workspace['id']}/workflows/{other['id']}",
        headers=headers,
        json={
            "slug": "english-answer-filler",
            "graph": other["draft_graph"],
            "expected_version": other["draft_version"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Workflow slug is already in use"

    renamed = client.put(
        f"/api/v1/workspaces/{first_workspace['id']}/workflows/{workflow['id']}",
        headers=headers,
        json={
            "slug": "english-answer-filler-v2",
            "graph": workflow["draft_graph"],
            "expected_version": workflow["draft_version"],
        },
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["slug"] == "english-answer-filler-v2"
    assert client.get("/v1/apps/english-answer-filler").status_code == 404
    assert client.get("/v1/apps/english-answer-filler-v2").status_code == 200


def test_workflow_delete_requires_editor_and_hides_published_app(client: TestClient):
    owner = register(client, "delete-owner@example.com", "Delete Owner")
    viewer = register(client, "delete-viewer@example.com", "Delete Viewer")
    owner_headers = auth(owner)
    viewer_headers = auth(viewer)
    workspace_id = client.get("/api/v1/workspaces", headers=owner_headers).json()[0]["id"]

    invitation = client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": "delete-viewer@example.com", "role": "viewer", "max_uses": 1},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        f"/api/v1/workspaces/invitations/{invitation.json()['token']}/accept",
        headers=viewer_headers,
    )
    assert accepted.status_code == 200, accepted.text

    workflow_url = f"/api/v1/workspaces/{workspace_id}/workflows"
    created = client.post(
        workflow_url,
        headers=owner_headers,
        json={"name": "Disposable workflow", "slug": "disposable-workflow"},
    )
    assert created.status_code == 201, created.text
    workflow = created.json()
    published = client.post(
        f"{workflow_url}/{workflow['id']}/publish",
        headers=owner_headers,
        json={"change_note": "Before deletion"},
    )
    assert published.status_code == 200, published.text
    assert client.get("/v1/apps/disposable-workflow").status_code == 200

    forbidden = client.delete(f"{workflow_url}/{workflow['id']}", headers=viewer_headers)
    assert forbidden.status_code == 403
    assert client.get(f"{workflow_url}/{workflow['id']}", headers=owner_headers).status_code == 200

    deleted = client.delete(f"{workflow_url}/{workflow['id']}", headers=owner_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["message"] == "Workflow deleted; versions and run history are retained"
    assert all(item["id"] != workflow["id"] for item in client.get(workflow_url, headers=owner_headers).json())
    assert client.get(f"{workflow_url}/{workflow['id']}", headers=owner_headers).status_code == 404
    assert client.get("/v1/apps/disposable-workflow").status_code == 404
    assert client.delete(f"{workflow_url}/{workflow['id']}", headers=owner_headers).status_code == 404


def test_workflow_folders_enforce_scope_permissions_and_non_empty_deletion(client: TestClient):
    owner = register(client, "folder-owner@example.com", "Folder Owner")
    viewer = register(client, "folder-viewer@example.com", "Folder Viewer")
    owner_headers = auth(owner)
    viewer_headers = auth(viewer)
    workspace_id = client.get("/api/v1/workspaces", headers=owner_headers).json()[0]["id"]
    workflows_url = f"/api/v1/workspaces/{workspace_id}/workflows"
    folders_url = f"{workflows_url}/folders"

    invitation = client.post(
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": "folder-viewer@example.com", "role": "viewer", "max_uses": 1},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        f"/api/v1/workspaces/invitations/{invitation.json()['token']}/accept",
        headers=viewer_headers,
    )
    assert accepted.status_code == 200, accepted.text
    assert client.get(folders_url, headers=viewer_headers).status_code == 200
    assert client.post(folders_url, headers=viewer_headers, json={"name": "Denied"}).status_code == 403

    created_folder = client.post(
        folders_url, headers=owner_headers, json={"name": "  Operations  "}
    )
    assert created_folder.status_code == 201, created_folder.text
    folder = created_folder.json()
    assert folder["name"] == "Operations"
    assert folder["workflow_count"] == 0
    duplicate = client.post(folders_url, headers=owner_headers, json={"name": "Operations"})
    assert duplicate.status_code == 409

    renamed = client.patch(
        f"{folders_url}/{folder['id']}", headers=owner_headers, json={"name": "Delivery"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Delivery"

    workflow_response = client.post(
        workflows_url,
        headers=owner_headers,
        json={"name": "Filed workflow", "slug": "filed-workflow"},
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    assert workflow["folder_id"] is None
    moved = client.patch(
        f"{workflows_url}/{workflow['id']}/folder",
        headers=owner_headers,
        json={"folder_id": folder["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["folder_id"] == folder["id"]
    assert moved.json()["draft_version"] == workflow["draft_version"]
    assert client.get(folders_url, headers=owner_headers).json()[0]["workflow_count"] == 1
    non_empty = client.delete(f"{folders_url}/{folder['id']}", headers=owner_headers)
    assert non_empty.status_code == 409

    second_workspace = client.post(
        "/api/v1/workspaces",
        headers=owner_headers,
        json={"name": "Folder Scope Workspace", "timezone": "Asia/Singapore"},
    ).json()
    foreign_folder = client.post(
        f"/api/v1/workspaces/{second_workspace['id']}/workflows/folders",
        headers=owner_headers,
        json={"name": "Foreign"},
    ).json()
    foreign_move = client.patch(
        f"{workflows_url}/{workflow['id']}/folder",
        headers=owner_headers,
        json={"folder_id": foreign_folder["id"]},
    )
    assert foreign_move.status_code == 404

    moved_to_root = client.patch(
        f"{workflows_url}/{workflow['id']}/folder",
        headers=owner_headers,
        json={"folder_id": None},
    )
    assert moved_to_root.status_code == 200, moved_to_root.text
    assert moved_to_root.json()["folder_id"] is None
    assert client.delete(f"{folders_url}/{folder['id']}", headers=owner_headers).status_code == 204

    soft_delete_folder = client.post(
        folders_url, headers=owner_headers, json={"name": "Soft deleted contents"}
    ).json()
    soft_deleted_workflow = client.post(
        workflows_url,
        headers=owner_headers,
        json={"name": "Soft deleted filed workflow", "slug": "soft-deleted-filed-workflow"},
    ).json()
    client.patch(
        f"{workflows_url}/{soft_deleted_workflow['id']}/folder",
        headers=owner_headers,
        json={"folder_id": soft_delete_folder["id"]},
    )
    client.delete(f"{workflows_url}/{soft_deleted_workflow['id']}", headers=owner_headers)
    folder_after_soft_delete = next(
        item
        for item in client.get(folders_url, headers=owner_headers).json()
        if item["id"] == soft_delete_folder["id"]
    )
    assert folder_after_soft_delete["workflow_count"] == 0
    assert (
        client.delete(f"{folders_url}/{soft_delete_folder['id']}", headers=owner_headers).status_code
        == 204
    )


def test_chat_workflow_uses_llm_template_and_binds_default_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    session = register(client, "chat-template-owner@example.com", "Chat Template Owner")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflows_url = f"/api/v1/workspaces/{workspace_id}/workflows"

    unconfigured = client.post(
        workflows_url,
        headers=headers,
        json={"name": "Chat template without model", "app_type": "chat"},
    )
    assert unconfigured.status_code == 201, unconfigured.text
    unconfigured_graph = unconfigured.json()["draft_graph"]
    assert [node["type"] for node in unconfigured_graph["nodes"]] == ["start", "llm", "end"]
    assert unconfigured_graph["edges"] == [
        {"id": "start-llm", "source": "start", "target": "llm"},
        {"id": "llm-end", "source": "llm", "target": "end"},
    ]
    start = unconfigured_graph["nodes"][0]
    llm = unconfigured_graph["nodes"][1]
    end = unconfigured_graph["nodes"][2]
    assert start["data"]["config"]["input_fields"][0]["required"] is True
    assert llm["data"]["config"]["provider_id"] == ""
    assert llm["data"]["config"]["model"] == ""
    assert llm["data"]["config"]["messages"][-1]["content"] == "{{inputs.message}}"
    assert end["data"]["config"]["outputs"] == [
        {"name": "message", "type": "String", "value": "{{LLM.text}}"}
    ]
    workflow_engine.validate_draft_graph(unconfigured_graph)

    provider = client.post(
        f"/api/v1/workspaces/{workspace_id}/models",
        headers=headers,
        json={
            "name": "Chat provider",
            "base_url": "https://models.example/v1",
            "api_key": "test-secret",
            "default_model": "chat-model",
        },
    )
    assert provider.status_code == 201, provider.text

    configured = client.post(
        workflows_url,
        headers=headers,
        json={"name": "Chat template with model", "app_type": "chat"},
    )
    assert configured.status_code == 201, configured.text
    configured_graph = configured.json()["draft_graph"]
    configured_llm = configured_graph["nodes"][1]
    assert configured_llm["data"]["config"]["provider_id"] == provider.json()["id"]
    assert configured_llm["data"]["config"]["model"] == "chat-model"
    workflow_engine.validate_graph(configured_graph)

    captured: dict[str, str] = {}

    def fake_execute_llm(runtime: dict, config: dict) -> dict:
        captured["message"] = config["messages"][-1]["content"]
        return {"text": "Template reply"}

    monkeypatch.setattr(workflow_engine, "execute_llm", fake_execute_llm)
    output, trace = execute_graph(
        configured_graph,
        {"message": "Hello template"},
        model_providers={provider.json()["id"]: {"name": "Chat provider"}},
    )
    assert captured["message"] == "Hello template"
    assert output == {"message": "Template reply"}
    assert [item["node_id"] for item in trace] == ["start", "llm", "end"]

    regular = client.post(
        workflows_url,
        headers=headers,
        json={"name": "Regular workflow after chat template", "app_type": "workflow"},
    )
    assert regular.status_code == 201, regular.text
    assert [node["type"] for node in regular.json()["draft_graph"]["nodes"]] == [
        "start",
        "end",
    ]


def test_versioned_script_and_workflow_publish(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    script = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts",
        headers=auth(session),
        json={
            "name": "Greeting",
            "source_code": "def main(inputs, context):\n    return {'message': inputs['name']}",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            "output_schema": {"type": "object"},
            "network_enabled": True,
        },
    )
    assert script.status_code == 201, script.text
    script_version = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script.json()['id']}/versions/1",
        headers=auth(session),
    )
    assert script_version.status_code == 200, script_version.text
    assert script_version.json()["network_enabled"] is True
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=auth(session),
        json={"name": "Greeting workflow"},
    )
    assert workflow.status_code == 201, workflow.text
    workflow_data = workflow.json()
    graph = workflow_data["draft_graph"]
    graph["nodes"].insert(
        1,
        {
            "id": "script-1",
            "type": "script",
            "position": {"x": 250, "y": 160},
            "data": {"label": "Greeting", "config": {"script_id": script.json()["id"]}},
        },
    )
    graph["edges"] = [
        {"id": "a", "source": "start", "target": "script-1"},
        {"id": "b", "source": "script-1", "target": "end"},
    ]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_data['id']}",
        headers=auth(session),
        json={"graph": graph, "expected_version": workflow_data["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_data['id']}/publish",
        headers=auth(session),
        json={"change_note": "First release"},
    )
    assert published.status_code == 200, published.text
    reference = published.json()["resolved_references"]["script-1"]
    assert reference["version"] == 1


def test_pingcode_worklog_workflow_template_installs_dedicated_network_script(
    client: TestClient,
):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]

    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={
            "name": "PingCode worklog workflow",
            "template_id": "pingcode_worklog",
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    graph = workflow["draft_graph"]
    assert [node["type"] for node in graph["nodes"]] == ["start", "script", "end"]
    start = graph["nodes"][0]
    assert start["data"]["config"]["input_fields"][0]["type"] == "month"
    script_node = graph["nodes"][1]
    assert script_node["data"]["config"]["inputs"]["project_identifier"] == "NEWDMS"

    scripts = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts",
        headers=headers,
    ).json()
    script = next(item for item in scripts if item["slug"] == "pingcode-worklog-filler")
    version = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/versions/1",
        headers=headers,
    )
    assert version.status_code == 200, version.text
    assert version.json()["network_enabled"] is True

    variables = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/environment-variables",
        headers=headers,
    )
    assert variables.status_code == 200, variables.text
    variable_values = {item["name"]: item for item in variables.json()}
    assert {
        "PINGCODE_ACCESS_TOKEN",
        "PINGCODE_CLIENT_ID",
        "PINGCODE_CLIENT_SECRET",
        "PINGCODE_ASSIGNEE_ID",
        "PINGCODE_ASSIGNEE_EMAIL",
        "PINGCODE_WORKLOAD_TYPE_ID",
    } == set(variable_values)
    assert all(item["value"] == "" for item in variable_values.values())
    assert all(item["has_value"] is False for item in variable_values.values())


def test_system_info_workflow_template_uses_windows_host_agent(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "System information", "template_id": "system_info"},
    )
    assert response.status_code == 201, response.text
    graph = response.json()["draft_graph"]
    assert [node["type"] for node in graph["nodes"]] == ["start", "host_info", "end"]
    assert graph["nodes"][1]["data"]["config"]["timeout_seconds"] == 10
    outputs = graph["nodes"][2]["data"]["config"]["outputs"]
    assert [output["name"] for output in outputs] == [
        "primary_ipv4", "primary_interface", "adapters", "source"
    ]


def test_rdp_disconnect_workflow_template_uses_windows_agent(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Disconnect RDP", "template_id": "rdp_disconnect"},
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    graph = workflow["draft_graph"]
    assert workflow["description"] == (
        "通过本机 Windows Agent 断开当前活跃的远程桌面连接，不注销用户。"
    )
    assert [node["type"] for node in graph["nodes"]] == ["start", "rdp_disconnect", "end"]
    assert graph["nodes"][1]["data"]["config"] == {"timeout_seconds": 10}
    outputs = graph["nodes"][2]["data"]["config"]["outputs"]
    assert [output["name"] for output in outputs] == [
        "ok", "disconnected_count", "sessions", "message"
    ]


def test_multi_file_script_upload_versions_diff_and_restore(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "main.py",
            "from helpers.maths import double\n\ndef main(inputs, context):\n    return {'value': double(inputs['value'])}\n",
        )
        archive.writestr("helpers/__init__.py", "")
        archive.writestr("helpers/maths.py", "def double(value):\n    return value * 2\n")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/upload",
        headers=auth(session),
        files={"file": ("multi-file.zip", archive_buffer.getvalue(), "application/zip")},
        data={"name": "Multi file utility", "entrypoint": "main:main"},
    )
    assert response.status_code == 201, response.text
    script = response.json()
    page = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/versions",
        headers=auth(session),
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert "source_code" not in page.json()["items"][0]
    detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/versions/1",
        headers=auth(session),
    )
    assert detail.status_code == 200, detail.text
    assert set(detail.json()["source_files"]) == {
        "main.py",
        "helpers/__init__.py",
        "helpers/maths.py",
    }
    files = detail.json()["source_files"]
    files["helpers/maths.py"] = "def double(value):\n    return value * 3\n"
    updated = client.put(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}",
        headers=auth(session),
        json={
            "name": script["name"],
            "source_code": detail.json()["source_code"],
            "source_files": files,
            "entrypoint": "main:main",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "network_enabled": True,
            "expected_version": 1,
        },
    )
    assert updated.status_code == 200, updated.text
    updated_detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/versions/2",
        headers=auth(session),
    ).json()
    assert updated_detail["network_enabled"] is True
    diff = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/diff",
        params={"from_version": 1, "to_version": 2},
        headers=auth(session),
    )
    assert diff.status_code == 200, diff.text
    assert "return value * 3" in diff.json()["diff"]
    restored = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/restore",
        headers=auth(session),
        json={"source_version": 1, "expected_version": 2},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["latest_version"] == 3
    restored_detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts/{script['id']}/versions/3",
        headers=auth(session),
    ).json()
    assert "return value * 2" in restored_detail["source_files"]["helpers/maths.py"]
    assert restored_detail["network_enabled"] is False


def test_script_runtime_forwards_versioned_network_permission(monkeypatch):
    captured: dict = {}

    def fake_execute_sandbox(source, entrypoint, inputs, **kwargs):
        captured.update(kwargs)
        return {"result": "ok", "_logs": [], "_elapsed_ms": 1}

    monkeypatch.setattr(workflow_engine, "execute_sandbox", fake_execute_sandbox)
    result = workflow_engine.execute_script_runtime(
        {
            "source": "def main(inputs, context): return {'result': 'ok'}",
            "source_files": {"main.py": "def main(inputs, context): return {'result': 'ok'}"},
            "entrypoint": "main:main",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "network_enabled": True,
        },
        {},
    )

    assert result["result"] == "ok"
    assert captured["network_enabled"] is True


def test_month_start_input_accepts_year_month_and_rejects_invalid_default():
    config = {
        "triggers": ["form"],
        "input_fields": [
            {
                "name": "start_month",
                "label": "Start month",
                "type": "month",
                "required": True,
                "default_value": "2026-08",
            }
        ],
    }
    workflow_engine.validate_start_config(config)

    invalid = deepcopy(config)
    invalid["input_fields"][0]["default_value"] = "2026-13"
    with pytest.raises(HTTPException, match="YYYY-MM"):
        workflow_engine.validate_start_config(invalid)


def test_script_bundle_validation_accepts_cross_file_imports():
    digest = validate_script(
        "from tools.text import clean\n\ndef main(inputs, context):\n    return {'text': clean(inputs['text'])}\n",
        "main:main",
        {"type": "object"},
        {"type": "object"},
        {
            "main.py": "from tools.text import clean\n\ndef main(inputs, context):\n    return {'text': clean(inputs['text'])}\n",
            "tools/__init__.py": "",
            "tools/text.py": "def clean(value):\n    return value.strip()\n",
        },
    )
    assert len(digest) == 64


@pytest.mark.parametrize("path", ["/absolute/main.py", "C:/scripts/main.py", "../main.py"])
def test_script_bundle_validation_rejects_unsafe_paths(path: str):
    with pytest.raises(HTTPException) as error:
        validate_script(
            "def main(inputs, context):\n    return {}\n",
            "main:main",
            {"type": "object"},
            {"type": "object"},
            {path: "def main(inputs, context):\n    return {}\n"},
        )
    assert error.value.status_code == 422


def test_script_zip_rejects_too_many_python_files(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.py", "def main(inputs, context):\n    return {}\n")
        for index in range(100):
            archive.writestr(f"module_{index}.py", f"VALUE = {index}\n")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/upload",
        headers=auth(session),
        files={"file": ("too-many.zip", archive_buffer.getvalue(), "application/zip")},
        data={"name": "Too many files", "entrypoint": "main:main"},
    )
    assert response.status_code == 422
    assert "too many Python files" in response.json()["detail"]


def test_unsaved_script_draft_can_be_enqueued_for_testing(client: TestClient, monkeypatch):
    import app.api.routes.scripts as script_routes

    session = register(client, "script-draft@example.com", "Script Draft")
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    captured: dict = {}

    def capture_test(task_id, captured_workspace_id, script_id, payload):
        captured.update(
            task_id=task_id,
            workspace_id=captured_workspace_id,
            script_id=script_id,
            payload=payload,
        )

    monkeypatch.setattr(script_routes, "create_script_test", capture_test)
    monkeypatch.setattr(script_routes.celery, "send_task", lambda *args, **kwargs: None)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/test",
        headers=auth(session),
        json={
            "source_files": {
                "main.py": "from helpers import value\n\ndef main(inputs, context):\n    return {'value': value()}\n",
                "helpers.py": "def value():\n    return 42\n",
            },
            "entrypoint": "main:main",
            "input_schema": {"type": "object"},
            "output_schema": {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
            "inputs": {},
        },
    )
    assert response.status_code == 202, response.text
    assert captured["workspace_id"] == workspace_id
    assert captured["script_id"] is None
    assert captured["payload"]["source_files"]["helpers.py"].startswith("def value")


def test_script_test_file_upload_is_hydrated_for_the_sandbox(
    client: TestClient, monkeypatch
):
    import app.api.routes.scripts as script_routes

    session = register(client, "script-file@example.com", "Script File")
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/test-files",
        headers=auth(session),
        files={"file": ("input.docx", b"test", "application/octet-stream")},
    )
    assert uploaded.status_code == 201, uploaded.text
    captured: dict = {}

    def capture_test(task_id, captured_workspace_id, script_id, payload):
        captured.update(payload=payload)

    monkeypatch.setattr(script_routes, "create_script_test", capture_test)
    monkeypatch.setattr(script_routes.celery, "send_task", lambda *args, **kwargs: None)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/scripts/test",
        headers=auth(session),
        json={
            "source_code": "def main(inputs, context):\n    return {'ok': True}\n",
            "entrypoint": "main:main",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "object",
                        "x-ordo-type": "file",
                        "required": ["filename", "content_type"],
                    }
                },
                "required": ["source"],
            },
            "output_schema": {"type": "object"},
            "inputs": {"source": uploaded.json()},
        },
    )
    assert response.status_code == 202, response.text
    assert captured["payload"]["inputs"]["source"]["__ordo_object_key"]


def test_workflow_environment_variables_are_encrypted_masked_and_resolved(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=auth(session),
        json={"name": "Environment workflow"},
    ).json()
    base = f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/environment-variables"
    greeting = client.post(base, headers=auth(session), json={"name": "GREETING", "value_type": "string", "value": "hello", "description": "Greeting text"})
    secret = client.post(base, headers=auth(session), json={"name": "API_SECRET", "value_type": "secret", "value": "never-return-this"})
    assert greeting.status_code == 201, greeting.text
    assert secret.status_code == 201, secret.text
    assert secret.json()["value"] == "••••••••"
    assert "never-return-this" not in client.get(base, headers=auth(session)).text

    graph = workflow["draft_graph"]
    start = next(node for node in graph["nodes"] if node["type"] == "start")
    start["data"]["config"]["triggers"] = ["api"]
    end = next(node for node in graph["nodes"] if node["type"] == "end")
    end["data"]["config"]["outputs"] = [
        {"name": "message", "type": "String", "value": "{{env.GREETING}}"},
        {"name": "user_id", "type": "String", "value": "{{sys.user_id}}"},
        {"name": "run_id", "type": "String", "value": "{{sys.workflow_run_id}}"},
        {"name": "timestamp", "type": "Number", "value": "{{sys.timestamp}}"},
    ]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=auth(session),
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=auth(session),
        json={"inputs": {"message": "ignored"}},
    )
    assert run.status_code == 200, run.text
    assert run.json()["outputs"]["message"] == "hello"
    assert run.json()["outputs"]["user_id"] == session["user"]["id"]
    assert run.json()["outputs"]["run_id"] == run.json()["id"]
    assert isinstance(run.json()["outputs"]["timestamp"], int)
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=auth(session),
        json={"change_note": "Environment release"},
    )
    assert published.status_code == 200, published.text
    public_run = client.post(f"/v1/apps/{workflow['slug']}/run", json={"inputs": {"message": "ignored"}, "user": "public-user-1"})
    assert public_run.status_code == 200, public_run.text
    assert public_run.json()["outputs"]["message"] == "hello"
    assert public_run.json()["outputs"]["user_id"] == "public-user-1"
    assert public_run.json()["outputs"]["run_id"] == public_run.json()["run_id"]


def test_agent_script_tools_are_pinned_on_publish():
    graph = {
        "nodes": [
            {
                "id": "agent-1",
                "type": "agent",
                "data": {
                    "config": {
                        "tools": [
                            {
                                "id": "tool-1",
                                "type": "script",
                                "reference_id": "script-1",
                                "enabled": True,
                            }
                        ]
                    }
                },
            }
        ]
    }
    references = workflow_engine.resolve_script_references(
        graph, {"script-1": ("script-version-2", 2)}
    )
    assert references["agent-1:tool-1"] == {
        "kind": "agent_tool",
        "tool_id": "tool-1",
        "script_id": "script-1",
        "script_version_id": "script-version-2",
        "version": 2,
    }


def test_unknown_nodes_are_rejected_in_drafts_published_graphs_and_execution():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"label": "Start", "config": {"triggers": ["form"], "input_fields": []}}},
            {"id": "mystery", "type": "mystery", "data": {"label": "Mystery", "config": {}}},
            {"id": "end", "type": "end", "data": {"label": "End", "config": {"outputs": [{"name": "done", "type": "String", "value": "done"}]}}},
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "mystery"},
            {"id": "b", "source": "mystery", "target": "end"},
        ],
    }

    for validator in (workflow_engine.validate_draft_graph, workflow_engine.validate_graph):
        with pytest.raises(HTTPException, match="Unsupported node type: mystery"):
            validator(graph)
    with pytest.raises(HTTPException, match="Unsupported node type: mystery"):
        execute_node(graph["nodes"][1], {"inputs": {}, "env": {}, "sys": {}})


def test_workflow_execution_stops_when_cancellation_is_requested():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"label": "Start", "config": {"triggers": ["api"], "input_fields": []}}},
            {"id": "delay", "type": "delay", "data": {"label": "Delay", "config": {"seconds": 0.1}}},
            {"id": "end", "type": "end", "data": {"label": "End", "config": {"outputs": [{"name": "done", "type": "String", "value": "done"}]}}},
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "delay"},
            {"id": "b", "source": "delay", "target": "end"},
        ],
    }
    checks = 0

    def cancellation_requested() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(workflow_engine.WorkflowCancelled, match="cancelled"):
        execute_graph(graph, {}, cancellation_callback=cancellation_requested)
    assert checks == 4


def test_workspace_scope_blocks_foreign_script_access(client: TestClient):
    owner = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    member = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "correct-horse-battery"},
    ).json()
    owner_workspace = client.get("/api/v1/workspaces", headers=auth(owner)).json()[0]["id"]
    member_private = next(
        item["id"]
        for item in client.get("/api/v1/workspaces", headers=auth(member)).json()
        if item["role"] == "owner"
    )
    response = client.get(
        f"/api/v1/workspaces/{member_private}/scripts",
        headers=auth(owner),
    )
    assert response.status_code == 404
    assert owner_workspace != member_private


def test_protected_publish_accepts_scoped_api_key(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    workspace_id = client.get("/api/v1/workspaces", headers=auth(session)).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=auth(session),
        json={"name": "Protected workflow"},
    ).json()
    graph = workflow["draft_graph"]
    start = next(node for node in graph["nodes"] if node["type"] == "start")
    start["data"]["config"]["triggers"] = ["api"]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=auth(session),
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=auth(session),
        json={"access": "protected", "all_users_enabled": True},
    )
    assert published.status_code == 200, published.text
    denied = client.post(f"/v1/apps/{workflow['slug']}/run", json={"inputs": {"value": 7}})
    assert denied.status_code == 401
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        headers=auth(session),
        json={"name": "Production", "workflow_id": workflow["id"]},
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]
    allowed = client.post(
        f"/v1/apps/{workflow['slug']}/run",
        headers={"Authorization": f"Bearer {key}"},
        json={"inputs": {"value": 7}},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "succeeded"

    form_graph = deepcopy(graph)
    form_start = next(node for node in form_graph["nodes"] if node["type"] == "start")
    form_start["data"]["config"]["triggers"] = ["form"]
    form_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=auth(session),
        json={"graph": form_graph, "expected_version": saved.json()["draft_version"]},
    )
    assert form_saved.status_code == 200, form_saved.text
    workspace_members = client.get(
        f"/api/v1/workspaces/{workspace_id}/members", headers=auth(session)
    ).json()
    assert len(workspace_members) >= 2
    other_member_id = next(
        item["user"]["id"]
        for item in workspace_members
        if item["user"]["id"] != session["user"]["id"]
    )
    member_ids = [session["user"]["id"], other_member_id]
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    day_after = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    three_days = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    four_days = (datetime.now(UTC) + timedelta(days=4)).isoformat()
    form_published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=auth(session),
        json={
            "access": "protected",
            "user_grants": [
                {"user_id": member_ids[0], "expires_at": tomorrow},
                {"user_id": member_ids[1], "expires_at": day_after},
            ],
            "password_grants": [
                {"label": "Partner one", "password": "123456", "expires_at": three_days},
                {"label": "Partner two", "password": "partner-pass-2", "expires_at": four_days},
            ],
        },
    )
    assert form_published.status_code == 200, form_published.text

    form_url = f"/v1/apps/{workflow['slug']}/form"
    assert client.post(form_url, json={"inputs": {"value": 8}}).status_code == 401
    assert client.post(
        form_url,
        headers={"Authorization": f"Bearer {key}"},
        json={"inputs": {"value": 8}},
    ).status_code == 401
    form_run = client.post(
        form_url,
        headers=auth(session),
        json={"inputs": {"value": 8}},
    )
    assert form_run.status_code == 200, form_run.text
    assert form_run.json()["status"] == "succeeded"
    run_id = form_run.json()["run_id"]
    protected_run = client.get(
        f"/v1/apps/{workflow['slug']}/runs/{run_id}", headers=auth(session)
    )
    assert protected_run.status_code == 200, protected_run.text
    grants = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/access-grants",
        headers=auth(session),
    )
    assert grants.status_code == 200, grants.text
    assert [item["grant_type"] for item in grants.json()].count("user") == 2
    assert [item["grant_type"] for item in grants.json()].count("password") == 2
    assert all(item["expires_at"] for item in grants.json())

    assert client.post(
        f"/v1/apps/{workflow['slug']}/access", json={"password": "wrong-password"}
    ).status_code == 401
    password_access = client.post(
        f"/v1/apps/{workflow['slug']}/access", json={"password": "123456"}
    )
    assert password_access.status_code == 200, password_access.text
    app_access = {"X-App-Access": password_access.json()["access_token"]}
    password_run = client.post(
        form_url,
        headers=app_access,
        json={"inputs": {"value": 9}},
    )
    assert password_run.status_code == 200, password_run.text
    password_run_id = password_run.json()["run_id"]
    assert client.get(
        f"/v1/apps/{workflow['slug']}/runs/{password_run_id}", headers=app_access
    ).status_code == 200


def test_start_node_uses_one_trigger_and_validates_inputs(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Multi trigger workflow"},
    ).json()
    graph = workflow["draft_graph"]
    start = next(node for node in graph["nodes"] if node["type"] == "start")
    start["data"]["config"] = {
        "triggers": ["api"],
        "input_fields": [
            {
                "name": "message",
                "label": "Message",
                "type": "text",
                "required": True,
                "placeholder": "Ask something",
            },
            {
                "name": "attachment",
                "label": "Attachment",
                "type": "file",
                "required": False,
            },
            {
                "name": "tone",
                "label": "Tone",
                "type": "select",
                "required": False,
                "options": ["Formal", "Friendly"],
                "default_value": "Formal",
            },
            {
                "name": "short_code",
                "label": "Short code",
                "type": "text",
                "required": False,
                "max_length": 5,
            },
        ],
        "schedule": {
            "cron": "0 9 * * *",
            "timezone": "Asia/Singapore",
            "enabled": False,
            "inputs_json": '{"message":"Scheduled"}',
        },
    }
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"change_note": "Enable API trigger"},
    )
    assert published.status_code == 200, published.text

    description = client.get(f"/v1/apps/{workflow['slug']}")
    assert description.status_code == 200
    assert description.json()["triggers"] == ["api"]
    assert description.json()["input_fields"][0]["name"] == "message"
    assert client.post(f"/v1/apps/{workflow['slug']}/run", json={"inputs": {}}).status_code == 422
    api_run = client.post(
        f"/v1/apps/{workflow['slug']}/run", json={"inputs": {"message": "From API"}}
    )
    assert api_run.status_code == 200, api_run.text
    select_run = client.post(
        f"/v1/apps/{workflow['slug']}/run",
        json={"inputs": {"message": "From API", "tone": "Friendly"}},
    )
    assert select_run.status_code == 200, select_run.text
    invalid_select = client.post(
        f"/v1/apps/{workflow['slug']}/run",
        json={"inputs": {"message": "From API", "tone": "Unsupported"}},
    )
    assert invalid_select.status_code == 422
    too_long = client.post(
        f"/v1/apps/{workflow['slug']}/run",
        json={"inputs": {"message": "From API", "short_code": "TOO-LONG"}},
    )
    assert too_long.status_code == 422
    webhook_run = client.post(
        f"/v1/apps/{workflow['slug']}/webhook",
        json={"inputs": {"message": "From webhook"}},
    )
    assert webhook_run.status_code == 404, webhook_run.text
    runs = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs",
        headers=headers,
    ).json()["items"]
    assert {run["triggered_by"] for run in runs} >= {"api"}

    multiple_triggers = deepcopy(graph)
    multiple_start = next(node for node in multiple_triggers["nodes"] if node["type"] == "start")
    multiple_start["data"]["config"]["triggers"] = ["api", "webhook"]
    rejected = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": multiple_triggers, "expected_version": saved.json()["draft_version"]},
    )
    assert rejected.status_code == 422

    invalid_graph = deepcopy(graph)
    invalid_start = next(node for node in invalid_graph["nodes"] if node["type"] == "start")
    invalid_start["data"]["config"]["triggers"] = ["schedule"]
    invalid_start["data"]["config"]["schedule"]["cron"] = "not a cron"
    invalid = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": invalid_graph, "expected_version": saved.json()["draft_version"]},
    )
    assert invalid.status_code == 422

    invalid_options_graph = deepcopy(graph)
    invalid_options_start = next(
        node for node in invalid_options_graph["nodes"] if node["type"] == "start"
    )
    tone_field = next(
        field
        for field in invalid_options_start["data"]["config"]["input_fields"]
        if field["name"] == "tone"
    )
    tone_field["options"] = ["Formal", "Formal"]
    invalid_options = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": invalid_options_graph, "expected_version": saved.json()["draft_version"]},
    )
    assert invalid_options.status_code == 422

    form_graph = deepcopy(graph)
    form_start = next(node for node in form_graph["nodes"] if node["type"] == "start")
    form_start["data"]["config"]["triggers"] = ["form"]
    form_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": form_graph, "expected_version": saved.json()["draft_version"]},
    )
    assert form_saved.status_code == 200, form_saved.text
    form_published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"change_note": "Enable form trigger"},
    )
    assert form_published.status_code == 200, form_published.text
    assert client.post(
        f"/v1/apps/{workflow['slug']}/run",
        json={"inputs": {"message": "From form"}},
    ).status_code == 404
    form_run = client.post(
        f"/v1/apps/{workflow['slug']}/form",
        json={"inputs": {"message": "From form"}},
    )
    assert form_run.status_code == 200, form_run.text
    runs = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs",
        headers=headers,
    ).json()["items"]
    assert any(run["triggered_by"] == "form" for run in runs)


def test_draft_node_preview_records_single_node_trace(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Node preview workflow"},
    ).json()

    preview = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/nodes/end/run",
        headers=headers,
        json={"inputs": {"message": "Preview value"}},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["triggered_by"] == "node"
    assert preview.json()["outputs"] == {"message": "Preview value"}
    assert len(preview.json()["trace"]) == 1
    assert preview.json()["trace"][0]["node_id"] == "end"

    missing = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/nodes/missing/run",
        headers=headers,
        json={"inputs": {}},
    )
    assert missing.status_code == 404


def test_trace_input_is_resolved_and_environment_values_are_redacted():
    from app.services.workflow_engine import build_node_trace_input, build_node_trace_metadata

    node = {
        "id": "template",
        "type": "template",
        "data": {"config": {"inputs": [{"name": "name", "value": "{{inputs.name}}"}, {"name": "token", "value": "Bearer {{env.API_TOKEN}}"}], "template": "Hello {{ name }}"}},
    }
    trace_input = build_node_trace_input(node, {"inputs": {"name": "Codex"}, "env": {"API_TOKEN": "top-secret"}, "sys": {}})
    assert trace_input["inputs"][0]["value"] == "Codex"
    assert trace_input["inputs"][1]["value"] == "Bearer ••••••••"
    metadata = build_node_trace_metadata(node, trace_input, {"text": "ok", "_logs": ["token=top-secret"], "_usage": {"prompt_tokens": 4, "completion_tokens": 2}}, 12.5, 2, {"env": {"API_TOKEN": "top-secret"}})
    assert metadata["executor"] == "built-in"
    assert metadata["retry_count"] == 1
    assert metadata["usage"] == {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6}
    assert metadata["logs"] == ["token=••••••••"]


def test_node_names_are_unique_and_resolve_chinese_variable_references():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"label": "开始", "config": {"triggers": ["api"], "input_fields": [{"name": "message", "type": "text"}]}}},
            {"id": "assign", "type": "variable", "data": {"label": "变量赋值", "config": {"assignments": [{"name": "answer", "type": "String", "operation": "overwrite", "value": "{{开始.message}}"}]}}},
            {"id": "end", "type": "end", "data": {"label": "结束", "config": {"outputs": [{"name": "message", "type": "String", "value": "{{变量赋值.answer}}"}]}}},
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "assign"},
            {"id": "b", "source": "assign", "target": "end"},
        ],
    }
    result, _ = execute_graph(graph, {"message": "按名称引用成功"})
    assert result == {"message": "按名称引用成功"}

    duplicate = deepcopy(graph)
    duplicate["nodes"][1]["data"]["label"] = "开始"
    with pytest.raises(HTTPException, match="unique node names"):
        workflow_engine.validate_draft_graph(duplicate)


def test_file_stem_variable_uses_the_uploaded_filename_without_its_extension():
    context = {
        "上传英语试卷": {
            "exam_file": {"filename": r"uploads\期末试卷.v2.docx"}
        }
    }

    assert workflow_engine.resolve_value(
        "{{上传英语试卷.exam_file.stem}}_已作答.docx", context
    ) == "期末试卷.v2_已作答.docx"


def test_structured_end_outputs_are_resolved_and_validated(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Structured output workflow"},
    ).json()
    graph = deepcopy(workflow["draft_graph"])
    end = next(node for node in graph["nodes"] if node["type"] == "end")
    end["data"]["config"]["outputs"] = [
        {"name": "answer", "type": "String", "value": "{{inputs.message}}"},
        {"name": "summary", "type": "String", "value": "Received: {{inputs.message}}"},
        {"name": "count", "type": "Number", "value": 1},
    ]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=headers,
        json={"inputs": {"message": "Hello"}},
    )
    assert run.status_code == 200, run.text
    assert run.json()["outputs"] == {
        "answer": "Hello",
        "summary": "Received: Hello",
        "count": 1,
    }

    invalid_graph = deepcopy(graph)
    invalid_end = next(node for node in invalid_graph["nodes"] if node["type"] == "end")
    invalid_end["data"]["config"]["outputs"][1]["name"] = "answer"
    invalid = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": invalid_graph, "expected_version": saved.json()["draft_version"]},
    )
    assert invalid.status_code == 422


def test_condition_node_executes_only_the_selected_branch():
    graph = {
        "schema_version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "data": {"config": {"triggers": ["api"], "input_fields": [{"name": "score", "type": "number"}]}},
            },
            {
                "id": "condition",
                "type": "condition",
                "data": {"config": {"logical_operator": "and", "conditions": [
                    {"variable": "{{inputs.score}}", "operator": "greater_or_equal", "value": 60}
                ]}},
            },
            {"id": "passed", "type": "template", "data": {"config": {"template": "passed"}}},
            {"id": "failed", "type": "template", "data": {"config": {"template": "failed"}}},
            {"id": "pass_end", "type": "end", "data": {"config": {"outputs": [
                {"name": "result", "type": "String", "value": "{{passed.text}}"}
            ]}}},
            {"id": "fail_end", "type": "end", "data": {"config": {"outputs": [
                {"name": "result", "type": "String", "value": "{{failed.text}}"}
            ]}}},
        ],
        "edges": [
            {"source": "start", "target": "condition"},
            {"source": "condition", "sourceHandle": "true", "target": "passed"},
            {"source": "condition", "sourceHandle": "false", "target": "failed"},
            {"source": "passed", "target": "pass_end"},
            {"source": "failed", "target": "fail_end"},
        ],
    }

    passed_output, passed_trace = execute_graph(graph, {"score": 85})
    assert passed_output == {"result": "passed"}
    assert [item["node_id"] for item in passed_trace] == ["start", "condition", "passed", "pass_end"]
    assert passed_trace[1]["output"]["branch"] == "true"

    failed_output, failed_trace = execute_graph(graph, {"score": 40})
    assert failed_output == {"result": "failed"}
    assert [item["node_id"] for item in failed_trace] == ["start", "condition", "failed", "fail_end"]
    assert failed_trace[1]["output"]["branch"] == "false"


def test_classifier_routes_to_stable_category_handles():
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["api"], "input_fields": [{"name": "message", "type": "text"}]}}},
            {"id": "classifier", "type": "classifier", "data": {"config": {
                "input": "{{inputs.message}}",
                "categories": [
                    {"id": "sales", "name": "Sales", "description": "Pricing and purchases", "keywords": ["buy", "price"]},
                    {"id": "support", "name": "Support", "description": "Fallback support request", "keywords": ["broken", "error"]},
                ],
            }}},
            {"id": "sales_text", "type": "template", "data": {"config": {"template": "sales"}}},
            {"id": "support_text", "type": "template", "data": {"config": {"template": "support"}}},
            {"id": "sales_end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "type": "String", "value": "{{sales_text.text}}"}]}}},
            {"id": "support_end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "type": "String", "value": "{{support_text.text}}"}]}}},
        ],
        "edges": [
            {"source": "start", "target": "classifier"},
            {"source": "classifier", "sourceHandle": "category:sales", "target": "sales_text"},
            {"source": "classifier", "sourceHandle": "category:support", "target": "support_text"},
            {"source": "sales_text", "target": "sales_end"},
            {"source": "support_text", "target": "support_end"},
        ],
    }

    sales_output, sales_trace = execute_graph(graph, {"message": "I want to buy this"})
    assert sales_output == {"result": "sales"}
    assert sales_trace[1]["output"]["branch"] == "category:sales"
    assert sales_trace[1]["output"]["fallback"] is False
    assert [item["node_id"] for item in sales_trace] == ["start", "classifier", "sales_text", "sales_end"]

    fallback_output, fallback_trace = execute_graph(graph, {"message": "Something else"})
    assert fallback_output == {"result": "support"}
    assert fallback_trace[1]["output"]["branch"] == "category:support"
    assert fallback_trace[1]["output"]["fallback"] is True


def test_classifier_branches_can_converge_on_one_node():
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["api"]}}},
            {"id": "classifier", "type": "classifier", "data": {"config": {
                "input": "{{inputs.message}}",
                "categories": [
                    {"id": "sales", "name": "Sales", "keywords": ["buy"]},
                    {"id": "support", "name": "Support", "keywords": ["help"]},
                ],
            }}},
            {"id": "shared", "type": "template", "data": {"config": {"template": "shared"}}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [
                {"name": "result", "type": "String", "value": "{{shared.text}}"},
            ]}}},
        ],
        "edges": [
            {"source": "start", "target": "classifier"},
            {"source": "classifier", "sourceHandle": "category:sales", "target": "shared"},
            {"source": "classifier", "sourceHandle": "category:support", "target": "shared"},
            {"source": "shared", "target": "end"},
        ],
    }

    output, trace = execute_graph(graph, {"message": "buy now"})

    assert output == {"result": "shared"}
    assert [item["node_id"] for item in trace] == ["start", "classifier", "shared", "end"]
    assert trace[1]["output"]["branch"] == "category:sales"


def test_llm_config_supports_messages_and_structured_output():
    validate_llm_config(
        {
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "{{inputs.message}}"},
            ],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 2048,
            "response_format": "json_schema",
            "response_schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            "context": "{{SourceNode.text}}",
            "vision": {"enabled": True, "variable": "{{inputs.images}}", "detail": "high"},
            "reasoning": {"separate": True},
        }
    )
    validate_llm_config({"model": "legacy-model", "prompt": "Legacy prompt"})
    with pytest.raises(HTTPException):
        validate_llm_config({"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": ""}]})
    with pytest.raises(HTTPException):
        validate_llm_config({"model": "gpt-4.1-mini", "prompt": "Hello", "temperature": 3})
    with pytest.raises(HTTPException):
        validate_llm_config({"model": "gpt-4.1-mini", "prompt": "Hello", "vision": {"enabled": True, "variable": "", "detail": "high"}})
    with pytest.raises(HTTPException):
        validate_llm_config({"model": "gpt-4.1-mini", "prompt": "Hello", "reasoning": {"separate": "yes"}})


def test_document_and_answer_filler_configs_are_validated_separately():
    validate_document_config({"operation": "extract", "source": "{{inputs.file}}", "extract_mode": "text_tables", "ocr_fallback": True})
    validate_answer_filler_config({"source": "{{inputs.file}}", "answers": "{{llm.structured_output}}"})
    # Published legacy graphs keep this operation until they are republished.
    validate_document_config({"operation": "fill_answers", "source": "{{inputs.file}}", "answers": "{{llm.structured_output}}"})
    with pytest.raises(HTTPException):
        validate_answer_filler_config({"source": "{{inputs.file}}", "answers": ""})
    with pytest.raises(HTTPException):
        validate_document_config({"operation": "convert", "source": "{{inputs.file}}", "target_format": "pdf"})


def test_http_node_validates_and_executes_a_structured_request():
    validate_http_config({"url": "{{inputs.url}}"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "https://example.test/items?page=2"
        assert request.headers["authorization"] == "Bearer secret-token"
        assert request.headers["x-workflow"] == "test"
        assert request.read() == b'{"name":"Ordo"}'
        return httpx.Response(201, json={"id": 42}, headers={"X-Result": "created"})

    output = execute_http_request(
        {
            "method": "POST",
            "url": "https://example.test/items",
            "query": {"page": 2},
            "headers": {"X-Workflow": "test"},
            "auth": {"type": "bearer", "token": "secret-token"},
            "body_type": "json",
            "body": {"name": "Ordo"},
            "timeout_seconds": 10,
            "max_response_bytes": 4096,
        },
        transport=httpx.MockTransport(handler),
    )

    assert output["status_code"] == 201
    assert output["body"] == {"id": 42}
    assert output["headers"]["x-result"] == "created"
    assert output["url"] == "https://example.test/items?page=2"
    assert output["ok"] is True
    assert output["elapsed_ms"] >= 0

    with pytest.raises(HTTPException):
        validate_http_config({"url": "file:///etc/passwd"})
    with pytest.raises(HTTPException):
        validate_http_config({"url": "https://example.test", "auth": {"type": "bearer", "token": ""}})


def test_http_node_redacts_query_credentials_and_sensitive_response_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["access_token"] == "private-value"
        return httpx.Response(200, text="ok", headers={"Set-Cookie": "session=secret", "X-Result": "ok"})

    output = execute_http_request(
        {
            "url": "https://example.test/protected",
            "auth": {"type": "api_key", "key": "access_token", "value": "private-value", "location": "query"},
        },
        transport=httpx.MockTransport(handler),
    )
    assert "private-value" not in output["url"]
    assert "%5BREDACTED%5D" in output["url"]
    assert output["headers"]["set-cookie"] == "[REDACTED]"
    assert output["headers"]["x-result"] == "ok"


def test_node_retry_and_error_branch_continue_the_workflow():
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["api"], "input_fields": [{"name": "value", "type": "text"}]}}},
            {"id": "list", "type": "list", "data": {"config": {
                "source": "{{inputs.value}}",
                "operation": "sort",
                "retry": {"enabled": True, "max_retries": 2, "interval_seconds": 0},
                "error_strategy": "error_branch",
            }}},
            {"id": "success", "type": "template", "data": {"config": {"template": "success"}}},
            {"id": "recovery", "type": "template", "data": {"config": {"template": "recovered"}}},
            {"id": "success_end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "value": "{{success.text}}"}]}}},
            {"id": "recovery_end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "value": "{{recovery.text}}"}]}}},
        ],
        "edges": [
            {"source": "start", "target": "list"},
            {"source": "list", "target": "success"},
            {"source": "list", "sourceHandle": "error", "target": "recovery"},
            {"source": "success", "target": "success_end"},
            {"source": "recovery", "target": "recovery_end"},
        ],
    }

    output, trace = execute_graph(graph, {"value": "not-an-array"})
    assert output == {"result": "recovered"}
    assert [item["node_id"] for item in trace] == ["start", "list", "recovery", "recovery_end"]
    list_trace = trace[1]
    assert list_trace["status"] == "recovered"
    assert list_trace["attempts"] == 3
    assert list_trace["error_handled"] is True
    assert list_trace["output"]["branch"] == "error"
    assert list_trace["output"]["error_type"] == "HTTPException"


def test_template_jinja_bindings_and_variable_aggregation():
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["api"], "input_fields": [{"name": "name", "type": "text"}]}}},
            {"id": "empty", "type": "variable", "data": {"config": {"values": {"value": None}}}},
            {"id": "template", "type": "template", "data": {"config": {"inputs": [{"name": "name", "value": "{{inputs.name}}"}], "template": "Hello {{ name | upper }}!"}}},
            {"id": "aggregate", "type": "aggregate", "data": {"config": {"variables": ["{{empty.value}}", "{{template.text}}"]}}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "value": "{{aggregate.output}}"}]}}},
        ],
        "edges": [
            {"source": "start", "target": "empty"},
            {"source": "start", "target": "template"},
            {"source": "empty", "target": "aggregate"},
            {"source": "template", "target": "aggregate"},
            {"source": "aggregate", "target": "end"},
        ],
    }
    output, trace = execute_graph(graph, {"name": "Codex"})
    assert output == {"result": "Hello CODEX!"}
    aggregate_trace = next(item for item in trace if item["node_id"] == "aggregate")
    assert aggregate_trace["output"] == {"output": "Hello CODEX!", "values": [None, "Hello CODEX!"]}


def test_grouped_variable_aggregation_outputs_named_values():
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["api"], "input_fields": [{"name": "answer", "type": "text"}]}}},
            {"id": "aggregate", "type": "aggregate", "data": {"config": {"group_enabled": True, "groups": [{"name": "answer", "variables": ["{{inputs.missing}}", "{{inputs.answer}}"]}, {"name": "fallback", "variables": ["{{inputs.missing}}"]}]}}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [{"name": "answer", "value": "{{aggregate.answer}}"}]}}},
        ],
        "edges": [{"source": "start", "target": "aggregate"}, {"source": "aggregate", "target": "end"}],
    }
    output, trace = execute_graph(graph, {"answer": "done"})
    assert output == {"answer": "done"}
    assert trace[1]["output"] == {"answer": "done", "fallback": None, "output": {"answer": "done", "fallback": None}}


def test_variable_assignment_parameter_extraction_and_list_pipeline():
    variable = execute_node({
        "type": "variable",
        "data": {"config": {"assignments": [
            {"name": "items", "type": "Array", "operation": "overwrite", "value": '[{"score": 7}, {"score": 3}, {"score": 9}, {"score": 7}]'},
            {"name": "active", "type": "Boolean", "operation": "overwrite", "value": "yes"},
        ]}},
    }, {})
    assert variable["active"] is True
    assert len(variable["items"]) == 4

    listed = execute_node({
        "type": "list",
        "data": {"config": {
            "source": variable["items"],
            "filter": {"enabled": True, "field": "score", "operator": "greater_than", "value": 5},
            "sort": {"enabled": True, "key": "score", "order": "desc"},
            "unique": True,
            "limit": {"enabled": True, "count": 2},
            "nth": {"enabled": True, "index": 2},
        }},
    }, {})
    assert listed == {"items": [{"score": 9}, {"score": 7}], "item": {"score": 7}}

    extracted = execute_node({
        "type": "extract",
        "data": {"config": {
            "source": '{"customer": "Ada", "count": "3"}',
            "fields": [{"name": "customer", "type": "String"}, {"name": "count", "type": "Number"}],
        }},
    }, {})
    assert extracted == {"customer": "Ada", "count": 3}


def test_inline_code_validation_and_sandbox_execution(monkeypatch: pytest.MonkeyPatch):
    config = {
        "inputs": [{"name": "message", "type": "String", "value": "{{inputs.message}}"}],
        "source": 'def main(inputs, context):\n    print("running")\n    return {"answer": inputs["message"], "score": "7"}',
        "entrypoint": "main",
        "outputs": [{"name": "answer", "type": "String"}, {"name": "score", "type": "Number"}],
        "timeout_seconds": 30,
        "memory_mb": 256,
        "network_enabled": False,
    }
    validate_code_config(config)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "succeeded", "outputs": {"answer": "hello", "score": "7"}, "logs": ["running"], "elapsed_ms": 12}

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            assert kwargs["json"]["inputs"] == {"message": "hello"}
            assert kwargs["json"]["network_enabled"] is False
            return FakeResponse()

    monkeypatch.setattr(workflow_engine.httpx, "Client", FakeClient)
    output = execute_node({"type": "code", "data": {"config": config}}, {"inputs": {"message": "hello"}})
    assert output == {"answer": "hello", "score": 7, "_logs": ["running"], "_elapsed_ms": 12}


def test_iteration_container_executes_child_graph_for_each_item():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["form"], "input_fields": []}}},
            {"id": "iterate", "type": "iteration", "data": {"config": {
                "source": [1, 2, 3], "item_variable": "item", "mode": "parallel", "concurrency": 2,
                "output": "{{render.text}}",
            }}},
            {"id": "render", "type": "template", "parentNode": "iterate", "data": {"config": {
                "inputs": [{"name": "value", "value": "{{item}}"}], "template": "{{ value }}!",
            }}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [
                {"name": "result", "type": "Any", "value": "{{iterate.results}}"},
            ]}}},
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "iterate"},
            {"id": "b", "source": "iterate", "target": "end"},
        ],
    }
    result, trace = execute_graph(graph, {})
    assert result == {"result": ["1!", "2!", "3!"]}
    assert [item["node_id"] for item in trace] == ["start", "iterate", "end"]


def test_parallel_branches_continue_independently_and_wait_nodes_join(monkeypatch):
    original = workflow_engine.execute_node_with_policy

    def delayed(node, context, graph=None):
        if node.get("id") == "slow":
            sleep_for_test(0.2)
        elif node.get("id") == "fast":
            sleep_for_test(0.02)
        return original(node, context, graph)

    monkeypatch.setattr(workflow_engine, "execute_node_with_policy", delayed)

    def graph(wait_mode: str):
        return {
            "nodes": [
                {"id": "start", "type": "start", "data": {"config": {"triggers": ["form"], "input_fields": []}}},
                {"id": "slow", "type": "template", "data": {"config": {"inputs": [], "template": "slow"}}},
                {"id": "fast", "type": "template", "data": {"config": {"inputs": [], "template": "fast"}}},
                {"id": "wait", "type": "wait", "data": {"config": {"mode": wait_mode}}},
                {"id": "end", "type": "end", "data": {"config": {"outputs": [{"name": "done", "type": "Boolean", "value": "{{wait.completed}}"}]}}},
            ],
            "edges": [
                {"id": "a", "source": "start", "target": "slow"},
                {"id": "b", "source": "start", "target": "fast"},
                {"id": "c", "source": "slow", "target": "wait"},
                {"id": "d", "source": "fast", "target": "wait"},
                {"id": "e", "source": "wait", "target": "end"},
            ],
        }

    _, all_trace = execute_graph(graph("all"), {})
    all_ids = [item["node_id"] for item in all_trace]
    assert all_ids.index("fast") < all_ids.index("slow")
    assert all_ids.index("wait") > all_ids.index("slow")

    _, any_trace = execute_graph(graph("any"), {})
    any_ids = [item["node_id"] for item in any_trace]
    assert any_ids.index("fast") < any_ids.index("wait") < any_ids.index("slow")
    assert "end" in any_ids and "slow" in any_ids


def test_loop_container_stops_when_child_condition_becomes_true():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["form"], "input_fields": []}}},
            {"id": "repeat", "type": "loop", "data": {"config": {
                "condition": "{{check.done}}", "max_iterations": 5, "output": "{{check.done}}",
            }}},
            {"id": "check", "type": "variable", "parentNode": "repeat", "data": {"config": {
                "assignments": [{"name": "done", "type": "Boolean", "operation": "overwrite", "value": True}],
            }}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [
                {"name": "result", "type": "Any", "value": "{{repeat.result}}"},
                {"name": "iterations", "type": "Number", "value": "{{repeat.iterations}}"},
            ]}}},
        ],
        "edges": [
            {"id": "a", "source": "start", "target": "repeat"},
            {"id": "b", "source": "repeat", "target": "end"},
        ],
    }
    result, _ = execute_graph(graph, {})
    assert result == {"result": True, "iterations": 1}


def test_container_edges_cannot_cross_the_parent_boundary():
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"config": {"triggers": ["form"], "input_fields": []}}},
            {"id": "iterate", "type": "iteration", "data": {"config": {"source": [1], "item_variable": "item", "mode": "sequential", "concurrency": 1}}},
            {"id": "render", "type": "template", "parentNode": "iterate", "data": {"config": {"inputs": [{"name": "value", "value": "{{item}}"}], "template": "{{ value }}"}}},
            {"id": "end", "type": "end", "data": {"config": {"outputs": [{"name": "result", "type": "Any", "value": "{{iterate.results}}"}]}}},
        ],
        "edges": [
            {"id": "invalid", "source": "start", "target": "render"},
            {"id": "valid", "source": "iterate", "target": "end"},
        ],
    }
    with pytest.raises(HTTPException, match="container boundary"):
        workflow_engine.validate_graph(graph)


def test_incomplete_nodes_can_autosave_but_cannot_publish(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Incomplete draft"},
    ).json()
    graph = deepcopy(workflow["draft_graph"])
    graph["nodes"].append({
        "id": "template-draft",
        "type": "template",
        "position": {"x": 240, "y": 180},
        "data": {"label": "Template", "config": {"inputs": [{"name": "arg1", "value": ""}], "template": ""}},
    })
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"change_note": "Must remain invalid"},
    )
    assert published.status_code == 422


def test_published_version_can_be_restored_to_draft(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Restore workflow"},
    ).json()
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"change_note": "Baseline"},
    )
    assert published.status_code == 200, published.text

    edited_graph = deepcopy(workflow["draft_graph"])
    edited_graph["nodes"][0]["data"]["label"] = "Changed start"
    edited = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": edited_graph, "expected_version": workflow["draft_version"]},
    )
    assert edited.status_code == 200, edited.text

    restored = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/versions/{published.json()['id']}/restore",
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["draft_graph"]["nodes"][0]["data"]["label"] == "Start"
    assert restored.json()["draft_version"] == edited.json()["draft_version"] + 1


def test_canvas_annotations_are_not_executed(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Annotated workflow"},
    ).json()
    graph = deepcopy(workflow["draft_graph"])
    graph["nodes"].append(
        {
            "id": "note-1",
            "type": "note",
            "position": {"x": 200, "y": 20},
            "data": {"label": "Remember", "description": "Review output", "color": "yellow"},
        }
    )
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=headers,
        json={"inputs": {"message": "Hello"}},
    )
    assert run.status_code == 200, run.text
    assert [item["node_id"] for item in run.json()["trace"]] == ["start", "end"]


def test_management_resource_lifecycle_and_run_logs(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]

    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/knowledge", headers=headers
    ).status_code == 404

    model = client.post(
        f"/api/v1/workspaces/{workspace_id}/models",
        headers=headers,
        json={
            "name": "Local compatible",
            "base_url": "http://localhost:9999/v1",
            "api_key": "test-secret",
            "default_model": "test-model",
        },
    )
    assert model.status_code == 201, model.text
    assert client.delete(
        f"/api/v1/workspaces/{workspace_id}/models/{model.json()['id']}", headers=headers
    ).status_code == 200

    workflow = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows", headers=headers
    ).json()[0]
    logs = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs",
        headers=headers,
    )
    assert logs.status_code == 200
    assert isinstance(logs.json()["items"], list)
    assert logs.json()["limit"] == 20


@pytest.mark.asyncio
async def test_model_connection_falls_back_to_minimal_inference_when_catalog_is_missing():
    from app.services.model_providers import test_provider_connection

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(404, json={"error": {"message": "catalog disabled"}})
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            },
        )

    result = await test_provider_connection(
        base_url="https://models.example/v1",
        api_key="secret",
        default_model="test-model",
        config={},
        transport=httpx.MockTransport(handler),
    )

    assert result["status"] == "warning"
    assert result["inference_verified"] is True
    assert "inference succeeded" in result["warning"]


@pytest.mark.asyncio
async def test_model_catalog_fetch_returns_available_models():
    from app.services.model_providers import fetch_provider_models

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer catalog-secret"
        return httpx.Response(
            200,
            json={"data": [{"id": "model-b"}, {"id": "model-a"}]},
        )

    result = await fetch_provider_models(
        base_url="https://models.example/v1",
        api_key="catalog-secret",
        config={},
        transport=httpx.MockTransport(handler),
    )

    assert result["models"] == ["model-b", "model-a"]
    assert result["latency_ms"] >= 0


def test_model_catalog_endpoints_support_unsaved_and_saved_forms(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    import app.api.routes.models as model_routes

    calls: list[dict] = []

    async def fake_fetch(**kwargs):
        calls.append(kwargs)
        return {"models": ["catalog-model"], "latency_ms": 12.5}

    monkeypatch.setattr(model_routes, "fetch_provider_models", fake_fetch)
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    base = f"/api/v1/workspaces/{workspace_id}/models"

    unsaved = client.post(
        f"{base}/catalog",
        headers=headers,
        json={"base_url": "https://models.example/v1", "api_key": "draft-secret"},
    )
    assert unsaved.status_code == 200, unsaved.text
    assert unsaved.json()["models"] == ["catalog-model"]
    assert calls[-1]["api_key"] == "draft-secret"

    provider = client.post(
        base,
        headers=headers,
        json={
            "name": "Catalog provider",
            "base_url": "https://saved.example/v1",
            "api_key": "saved-secret",
            "default_model": "catalog-model",
        },
    ).json()
    saved = client.post(f"{base}/{provider['id']}/catalog", headers=headers, json={})
    assert saved.status_code == 200, saved.text
    assert calls[-1]["base_url"] == "https://saved.example/v1"
    assert calls[-1]["api_key"] == "saved-secret"


def test_model_provider_update_reference_protection_and_secret_masking(client: TestClient):
    session = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery"},
    ).json()
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    base = f"/api/v1/workspaces/{workspace_id}/models"
    created = client.post(
        base,
        headers=headers,
        json={
            "name": "Protected provider",
            "base_url": "https://models.example/v1/",
            "api_key": "never-return-provider-secret",
            "default_model": "test-model",
            "config": {"api_mode": "chat_completions"},
        },
    )
    assert created.status_code == 201, created.text
    provider = created.json()
    assert provider["base_url"] == "https://models.example/v1"
    assert provider["has_api_key"] is True
    assert "never-return-provider-secret" not in created.text

    updated = client.patch(
        f"{base}/{provider['id']}",
        headers=headers,
        json={"name": "Protected provider updated", "default_model": "test-model-v2"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["has_api_key"] is True
    duplicate = client.post(
        base,
        headers=headers,
        json={
            "name": "Protected provider updated",
            "base_url": "https://another.example/v1",
            "api_key": "",
            "default_model": "other-model",
        },
    )
    assert duplicate.status_code == 409

    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Provider reference protection"},
    ).json()
    graph = workflow["draft_graph"]
    graph["nodes"].insert(
        1,
        {
            "id": "writer",
            "type": "llm",
            "position": {"x": 250, "y": 160},
            "data": {
                "label": "Writer",
                "config": {
                    "provider_id": provider["id"],
                    "model": "test-model-v2",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            },
        },
    )
    graph["edges"] = [
        {"id": "a", "source": "start", "target": "writer"},
        {"id": "b", "source": "writer", "target": "end"},
    ]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    blocked = client.delete(f"{base}/{provider['id']}", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["references"][0]["name"] == workflow["name"]

    graph["nodes"] = [node for node in graph["nodes"] if node["id"] != "writer"]
    graph["edges"] = [{"id": "direct", "source": "start", "target": "end"}]
    unlinked = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": saved.json()["draft_version"]},
    )
    assert unlinked.status_code == 200, unlinked.text
    assert client.delete(f"{base}/{provider['id']}", headers=headers).status_code == 200


def test_llm_node_executes_the_configured_provider(monkeypatch: pytest.MonkeyPatch):
    import app.services.model_execution as model_execution

    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer runtime-secret"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "Hello from model"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            },
        )

    monkeypatch.setattr(
        model_execution.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), timeout=kwargs["timeout"]),
    )
    graph = {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "data": {"label": "Start", "config": {"triggers": ["api"], "input_fields": []}},
            },
            {
                "id": "writer",
                "type": "llm",
                "data": {
                    "label": "Writer",
                    "config": {
                        "provider_id": "provider-1",
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "{{inputs.message}}"}],
                    },
                },
            },
            {
                "id": "end",
                "type": "end",
                "data": {
                    "label": "End",
                    "config": {
                        "outputs": [{"name": "result", "type": "String", "value": "{{Writer.text}}"}]
                    },
                },
            },
        ],
        "edges": [
            {"source": "start", "target": "writer"},
            {"source": "writer", "target": "end"},
        ],
    }
    output, trace = execute_graph(
        graph,
        {"message": "Hello"},
        model_providers={
            "provider-1": {
                "base_url": "https://127.0.0.1/v1",
                "api_key": "runtime-secret",
                "default_model": "test-model",
                "config": {"api_mode": "chat_completions", "allow_private_network": True},
            }
        },
    )

    assert output == {"result": "Hello from model"}
    assert trace[1]["output"]["_usage"]["total_tokens"] == 7
    assert "runtime-secret" not in str(trace)


def test_image_node_generates_multiple_images_with_provider_credentials(monkeypatch: pytest.MonkeyPatch):
    import app.services.model_execution as model_execution

    calls: list[dict] = []

    def request(runtime: dict, path: str, payload: dict) -> dict:
        calls.append(payload)
        assert runtime["api_key"] == "runtime-secret"
        assert path == "/images/generations"
        return {"data": [{"b64_json": "UklGRg=="}]}

    monkeypatch.setattr(model_execution, "provider_request", request)
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"label": "Start", "config": {"triggers": ["api"], "input_fields": []}}},
            {"id": "generator", "type": "image", "data": {"label": "Generate", "config": {
                "provider_id": "provider-1", "model": "gpt-image-2", "prompt": "{{inputs.prompt}}",
                "size": "{{inputs.size}}", "count": "{{inputs.count}}", "quality": "high",
                "output_format": "webp", "output_compression": 80, "background": "auto",
            }}},
            {"id": "end", "type": "end", "data": {"label": "End", "config": {
                "outputs": [{"name": "images", "type": "Array", "value": "{{Generate.images}}"}],
            }}},
        ],
        "edges": [{"source": "start", "target": "generator"}, {"source": "generator", "target": "end"}],
    }
    output, trace = execute_graph(
        graph,
        {"prompt": "A clean product photo", "size": "1440x2560", "count": 2},
        model_providers={"provider-1": {"base_url": "https://example.com/v1", "api_key": "runtime-secret", "default_model": "gpt-image-2", "config": {}}},
    )

    assert len(calls) == 2
    assert all(call["n"] == 1 and call["size"] == "1440x2560" for call in calls)
    assert output == {"images": ["data:image/webp;base64,UklGRg==", "data:image/webp;base64,UklGRg=="]}
    assert trace[1]["output"]["count"] == 2


def test_png_image_generation_omits_unsupported_compression(monkeypatch: pytest.MonkeyPatch):
    import app.services.model_execution as model_execution

    calls: list[dict] = []

    def request(runtime: dict, path: str, payload: dict) -> dict:
        calls.append(payload)
        return {"data": [{"b64_json": "iVBORw=="}]}

    monkeypatch.setattr(model_execution, "provider_request", request)
    output = model_execution.execute_image_generation(
        {
            "base_url": "https://example.com/v1",
            "api_key": "runtime-secret",
            "default_model": "gpt-image-2",
            "config": {},
        },
        {
            "prompt": "A clean product photo",
            "size": "1024x1024",
            "output_format": "png",
            "output_compression": 80,
        },
    )

    assert "output_compression" not in calls[0]
    assert output["images"] == ["data:image/png;base64,iVBORw=="]


def test_image_generation_omits_unconfigured_size(monkeypatch: pytest.MonkeyPatch):
    import app.services.model_execution as model_execution

    calls: list[dict] = []

    def request(runtime: dict, path: str, payload: dict) -> dict:
        calls.append(payload)
        return {"data": [{"b64_json": "iVBORw=="}]}

    monkeypatch.setattr(model_execution, "provider_request", request)
    output = model_execution.execute_image_generation(
        {
            "base_url": "https://example.com/v1",
            "api_key": "runtime-secret",
            "default_model": "gpt-image-2",
            "config": {},
        },
        {
            "prompt": "A portrait product photo with a 2:3 aspect ratio",
            "output_format": "png",
        },
    )

    assert "size" not in calls[0]
    assert output["images"] == ["data:image/png;base64,iVBORw=="]


def test_image_config_allows_unconfigured_size():
    from app.services.workflow_engine import validate_image_config

    validate_image_config(
        {
            "provider_id": "provider-1",
            "model": "gpt-image-2",
            "prompt": "A portrait product photo with a 2:3 aspect ratio",
            "size": "",
            "output_format": "png",
        }
    )


def test_human_approval_pauses_and_resumes_the_selected_branch(client: TestClient):
    session = register(client, "approval-owner@example.com", "Approval Owner")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Approval resume workflow"},
    ).json()
    graph = {
        "schema_version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Start", "config": {"triggers": ["api"], "input_fields": []}},
            },
            {
                "id": "review",
                "type": "human",
                "position": {"x": 260, "y": 0},
                "data": {
                    "label": "Review",
                    "config": {
                        "submission_methods": ["studio"],
                        "form_content": "Please review {{inputs.message}}",
                        "actions": [
                            {"id": "approve", "label": "Approve", "value": "approved", "style": "primary"},
                            {"id": "reject", "label": "Reject", "value": "rejected", "style": "danger"},
                        ],
                        "timeout_minutes": 60,
                    },
                },
            },
            {
                "id": "approved",
                "type": "end",
                "position": {"x": 520, "y": -80},
                "data": {"label": "Approved", "config": {"outputs": [{"name": "decision", "type": "String", "value": "approved"}]}},
            },
            {
                "id": "rejected",
                "type": "end",
                "position": {"x": 520, "y": 80},
                "data": {"label": "Rejected", "config": {"outputs": [{"name": "decision", "type": "String", "value": "rejected"}]}},
            },
        ],
        "edges": [
            {"source": "start", "target": "review"},
            {"source": "review", "sourceHandle": "action:approve", "target": "approved"},
            {"source": "review", "sourceHandle": "action:reject", "target": "rejected"},
        ],
    }
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": workflow["draft_version"]},
    )
    assert saved.status_code == 200, saved.text

    waiting = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=headers,
        json={"inputs": {"message": "invoice 42"}},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["status"] == "waiting"
    assert waiting.json()["finished_at"] is None
    approvals = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/approvals",
        headers=headers,
    )
    assert approvals.status_code == 200, approvals.text
    approval = approvals.json()[0]
    assert approval["status"] == "pending"
    assert approval["request"]["form_content"] == "Please review invoice 42"

    resumed = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs/{waiting.json()['id']}/approvals/{approval['id']}/respond",
        headers=headers,
        json={"action_id": "approve", "data": {"reviewed": True}, "comment": "Looks good"},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "succeeded"
    assert resumed.json()["outputs"] == {"decision": "approved"}
    assert [item["node_id"] for item in resumed.json()["trace"]] == ["start", "review", "approved"]
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs/{waiting.json()['id']}/approvals/{approval['id']}/respond",
        headers=headers,
        json={"action_id": "reject"},
    ).status_code == 409


def test_subworkflow_maps_inputs_and_pins_the_published_version(client: TestClient):
    session = register(client, "subworkflow-owner@example.com", "Subworkflow Owner")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]

    child = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Reusable child"},
    ).json()
    child_graph = deepcopy(child["draft_graph"])
    child_start = next(node for node in child_graph["nodes"] if node["type"] == "start")
    child_start["data"]["config"] = {
        "triggers": ["api"],
        "input_fields": [{"name": "message", "label": "Message", "type": "text", "required": True}],
    }
    child_end = next(node for node in child_graph["nodes"] if node["type"] == "end")
    child_end["data"]["config"]["outputs"] = [
        {"name": "child_value", "type": "String", "value": "v1 {{inputs.message}}"}
    ]
    child_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{child['id']}",
        headers=headers,
        json={"graph": child_graph, "expected_version": child["draft_version"]},
    )
    assert child_saved.status_code == 200, child_saved.text
    child_v1 = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{child['id']}/publish",
        headers=headers,
        json={"access": "public", "change_note": "Child v1"},
    )
    assert child_v1.status_code == 200, child_v1.text

    parent = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Parent caller"},
    ).json()
    parent_graph = deepcopy(parent["draft_graph"])
    parent_start = next(node for node in parent_graph["nodes"] if node["type"] == "start")
    parent_start["data"]["config"] = {
        "triggers": ["api"],
        "input_fields": [{"name": "message", "label": "Message", "type": "text", "required": True}],
    }
    parent_end = next(node for node in parent_graph["nodes"] if node["type"] == "end")
    parent_end["data"]["config"]["outputs"] = [
        {"name": "result", "type": "String", "value": "{{call.child_value}}"}
    ]
    parent_graph["nodes"].append(
        {
            "id": "call",
            "type": "subworkflow",
            "position": {"x": 250, "y": 160},
            "data": {
                "label": "Call child",
                "config": {"workflow_id": child["id"], "inputs": {"message": "{{inputs.message}}"}},
            },
        }
    )
    parent_graph["edges"] = [
        {"source": "start", "target": "call"},
        {"source": "call", "target": "end"},
    ]
    parent_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}",
        headers=headers,
        json={"graph": parent_graph, "expected_version": parent["draft_version"]},
    )
    assert parent_saved.status_code == 200, parent_saved.text
    draft_run = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}/run",
        headers=headers,
        json={"inputs": {"message": "hello"}},
    )
    assert draft_run.status_code == 200, draft_run.text
    assert draft_run.json()["outputs"] == {"result": "v1 hello"}
    parent_v1 = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}/publish",
        headers=headers,
        json={"access": "public", "change_note": "Pin child v1"},
    )
    assert parent_v1.status_code == 200, parent_v1.text
    pinned = parent_v1.json()["resolved_references"]["_subworkflows"]["call"]
    assert pinned["workflow_version_id"] == child_v1.json()["id"]

    child_graph_v2 = deepcopy(child_saved.json()["draft_graph"])
    child_end_v2 = next(node for node in child_graph_v2["nodes"] if node["type"] == "end")
    child_end_v2["data"]["config"]["outputs"][0]["value"] = "v2 {{inputs.message}}"
    child_v2_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{child['id']}",
        headers=headers,
        json={"graph": child_graph_v2, "expected_version": child_saved.json()["draft_version"]},
    )
    assert child_v2_saved.status_code == 200, child_v2_saved.text
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{child['id']}/publish",
        headers=headers,
        json={"access": "public", "change_note": "Child v2"},
    ).status_code == 200

    published_run = client.post(
        f"/v1/apps/{parent['slug']}/run",
        json={"inputs": {"message": "world"}},
    )
    assert published_run.status_code == 200, published_run.text
    assert published_run.json()["outputs"] == {"result": "v1 world"}


def test_subworkflow_human_approval_resumes_across_the_nested_call(client: TestClient):
    session = register(client, "nested-approval@example.com", "Nested Approval")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    child = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Approval child"},
    ).json()
    child_graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "child-start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Child start", "config": {"triggers": ["api"], "input_fields": []}}},
            {
                "id": "child-review",
                "type": "human",
                "position": {"x": 220, "y": 0},
                "data": {"label": "Nested review", "config": {"submission_methods": ["studio"], "form_content": "Review nested call", "actions": [{"id": "approve", "label": "Approve", "value": "approved"}, {"id": "reject", "label": "Reject", "value": "rejected"}], "timeout_minutes": 60}},
            },
            {"id": "child-ok", "type": "end", "position": {"x": 460, "y": -60}, "data": {"label": "Approved end", "config": {"outputs": [{"name": "decision", "type": "String", "value": "approved"}]}}},
            {"id": "child-no", "type": "end", "position": {"x": 460, "y": 60}, "data": {"label": "Rejected end", "config": {"outputs": [{"name": "decision", "type": "String", "value": "rejected"}]}}},
        ],
        "edges": [
            {"source": "child-start", "target": "child-review"},
            {"source": "child-review", "sourceHandle": "action:approve", "target": "child-ok"},
            {"source": "child-review", "sourceHandle": "action:reject", "target": "child-no"},
        ],
    }
    child_saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{child['id']}",
        headers=headers,
        json={"graph": child_graph, "expected_version": child["draft_version"]},
    )
    assert child_saved.status_code == 200, child_saved.text

    parent = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Nested approval parent"},
    ).json()
    graph = deepcopy(parent["draft_graph"])
    end = next(node for node in graph["nodes"] if node["type"] == "end")
    end["data"]["config"]["outputs"] = [{"name": "decision", "type": "String", "value": "{{call.decision}}"}]
    graph["nodes"].append({"id": "call", "type": "subworkflow", "position": {"x": 250, "y": 160}, "data": {"label": "Call approval child", "config": {"workflow_id": child["id"], "inputs": {}}}})
    graph["edges"] = [{"source": "start", "target": "call"}, {"source": "call", "target": "end"}]
    saved = client.put(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}",
        headers=headers,
        json={"graph": graph, "expected_version": parent["draft_version"]},
    )
    assert saved.status_code == 200, saved.text
    waiting = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}/run",
        headers=headers,
        json={"inputs": {"message": "hello"}},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["status"] == "waiting"
    approval = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}/approvals",
        headers=headers,
    ).json()[0]
    assert approval["node_id"] == "call/child-review"
    resumed = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{parent['id']}/runs/{waiting.json()['id']}/approvals/{approval['id']}/respond",
        headers=headers,
        json={"action_id": "approve"},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "succeeded"
    assert resumed.json()["outputs"] == {"decision": "approved"}
    call_trace = next(item for item in resumed.json()["trace"] if item["node_id"] == "call")
    assert [item["node_id"] for item in call_trace["output"]["_trace"]] == [
        "child-start",
        "child-review",
        "child-ok",
    ]


def test_model_provider_request_honors_max_retries(monkeypatch):
    import app.services.model_execution as model_execution

    request = httpx.Request("POST", "https://models.example/v1/chat/completions")

    class Client:
        calls = 0

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            Client.calls += 1
            return httpx.Response(
                503 if Client.calls == 1 else 200,
                request=request,
                json={"ok": True},
            )

    monkeypatch.setattr(model_execution, "ensure_safe_runtime_destination", lambda runtime: None)
    monkeypatch.setattr(model_execution.httpx, "Client", Client)
    monkeypatch.setattr(model_execution, "sleep", lambda seconds: None)
    result = model_execution.provider_request(
        {
            "base_url": "https://models.example/v1",
            "api_key": "",
            "config": {"timeout_seconds": 5, "max_retries": 1},
        },
        "/chat/completions",
        {"model": "test"},
    )
    assert result == {"ok": True}
    assert Client.calls == 2


def test_model_provider_stream_emits_incremental_tokens(monkeypatch):
    import app.services.model_execution as model_execution

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(
                [
                    'data: {"choices":[{"delta":{"content":"hel"}}]}',
                    'data: {"choices":[{"delta":{"content":"lo"}}]}',
                    "data: [DONE]",
                ]
            )

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(model_execution, "ensure_safe_runtime_destination", lambda runtime: None)
    monkeypatch.setattr(model_execution.httpx, "Client", Client)
    tokens = []
    result = model_execution.provider_stream_request(
        {
            "base_url": "https://models.example/v1",
            "api_key": "",
            "config": {"timeout_seconds": 5, "max_retries": 0},
        },
        "/chat/completions",
        {"model": "test"},
        tokens.append,
    )
    assert tokens == ["hel", "lo"]
    assert result["choices"][0]["message"]["content"] == "hello"


def test_agent_executes_tool_and_returns_final_answer(monkeypatch):
    import app.services.model_execution as model_execution

    responses = iter(
        [
            {
                "text": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "add", "arguments": '{"a":2,"b":3}'},
                    }
                ],
            },
            {"text": "5", "tool_calls": []},
        ]
    )
    monkeypatch.setattr(model_execution, "execute_llm", lambda runtime, config: next(responses))
    calls = []

    def execute(tool, arguments):
        calls.append((tool["name"], arguments))
        return {"sum": arguments["a"] + arguments["b"]}

    result = model_execution.execute_agent(
        {"default_model": "test", "config": {"api_mode": "chat_completions"}},
        {
            "query": "add",
            "instructions": "Use tools",
            "tools": [{"id": "add", "name": "add", "enabled": True}],
            "return_intermediate_steps": True,
        },
        execute,
    )
    assert result["text"] == "5"
    assert calls == [("add", {"a": 2, "b": 3})]
    assert result["intermediate_steps"][0]["result"] == {"sum": 5}


def test_english_exam_template_runs_and_downloads_docx_in_studio_and_public(
    client: TestClient, monkeypatch
):
    session = register(client, "exam-owner@example.com", "Exam Owner")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    provider = client.post(
        f"/api/v1/workspaces/{workspace_id}/models",
        headers=headers,
        json={
            "name": "Exam provider",
            "base_url": "https://models.example/v1",
            "api_key": "test-secret",
            "default_model": "test-model",
            "config": {"capabilities": {"structured_output": True, "vision": False}},
        },
    )
    assert provider.status_code == 201, provider.text

    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={
            "name": "English exam auto answer",
            "template_id": "english_exam_answer_filler",
        },
    )
    assert workflow.status_code == 201, workflow.text
    workflow_data = workflow.json()
    assert [node["type"] for node in workflow_data["draft_graph"]["nodes"]] == [
        "start",
        "document",
        "llm",
        "script",
        "end",
    ]
    scripts = client.get(
        f"/api/v1/workspaces/{workspace_id}/scripts", headers=headers
    ).json()
    answer_script = next(
        script for script in scripts if script["slug"] == "english-exam-answer-filler"
    )
    assert workflow_data["draft_graph"]["nodes"][3]["data"]["config"]["script_id"] == answer_script["id"]

    monkeypatch.setattr(
        workflow_engine,
        "execute_llm",
        lambda runtime, config: {
            "text": '{"insertions":[{"question_number":"Reading","anchor_id":"P0002","anchor":"A. is  B. are","answer":"1. are"}]}',
            "structured_output": {
                "insertions": [
                    {
                        "question_number": "Reading",
                        "anchor_id": "P0002",
                        "anchor": "A. is  B. are",
                        "answer": "1. are",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        workflow_engine,
        "execute_script_runtime",
        lambda runtime, inputs: fill_docx_answers(
            inputs["source"],
            inputs["answers"],
            output_name=str(inputs.get("output_name") or ""),
        ),
    )

    document_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:r><w:t>Reading</w:t></w:r></w:p>
<w:p><w:r><w:t>A. is  B. are</w:t></w:r></w:p><w:sectPr />
</w:body></w:document>'''
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("word/document.xml", document_xml)

    upload = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_data['id']}/files",
        headers=headers,
        files={"file": ("exam.docx", document.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert upload.status_code == 201, upload.text
    run = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_data['id']}/run",
        headers=headers,
        json={"inputs": {"exam_file": upload.json()}},
    )
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "succeeded", run.text
    output_file = run.json()["outputs"]["file"]
    downloaded = client.get(output_file["download_url"], headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as package:
        assert b"Answer Reading: " in package.read("word/document.xml")

    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_data['id']}/publish",
        headers=headers,
        json={"change_note": "Public exam form", "access": "public"},
    )
    assert published.status_code == 200, published.text
    public_upload = client.post(
        f"/v1/apps/{workflow_data['slug']}/files",
        files={"file": ("exam.docx", document.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert public_upload.status_code == 201, public_upload.text
    public_run = client.post(
        f"/v1/apps/{workflow_data['slug']}/form",
        json={"inputs": {"exam_file": public_upload.json()}},
    )
    assert public_run.status_code == 200, public_run.text
    public_result = client.get(
        f"/v1/apps/{workflow_data['slug']}/runs/{public_run.json()['run_id']}"
    )
    assert public_result.status_code == 200, public_result.text
    public_file = public_result.json()["outputs"]["file"]
    public_download = client.get(public_file["download_url"])
    assert public_download.status_code == 200, public_download.text
    assert public_download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_public_runs_are_idempotent_and_guarded(client: TestClient, monkeypatch):
    session = register(client, "public-guard@example.com", "Public Guard")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Idempotent public form"},
    ).json()
    published = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/publish",
        headers=headers,
        json={"access": "public"},
    )
    assert published.status_code == 200, published.text

    url = f"/v1/apps/{workflow['slug']}/form"
    request_headers = {"Idempotency-Key": "submission-001"}
    first = client.post(
        url,
        headers=request_headers,
        json={"inputs": {"message": "hello"}},
    )
    repeated = client.post(
        url,
        headers=request_headers,
        json={"inputs": {"message": "hello"}},
    )
    conflicting = client.post(
        url,
        headers=request_headers,
        json={"inputs": {"message": "different"}},
    )
    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["run_id"] == first.json()["run_id"]
    assert conflicting.status_code == 409

    guarded = AsyncMock(
        side_effect=HTTPException(status_code=429, detail="Too many requests")
    )
    monkeypatch.setattr(public_routes, "enforce_public_rate_limit", guarded)
    limited = client.post(url, json={"inputs": {"message": "limited"}})
    assert limited.status_code == 429
    guarded.assert_awaited_once()


def test_workflow_runs_can_be_cancelled_and_retried(client: TestClient, monkeypatch):
    session = register(client, "run-control@example.com", "Run Control")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Controlled workflow"},
    ).json()
    enqueue = AsyncMock()
    monkeypatch.setattr(workflow_routes, "enqueue_persisted_workflow_run", enqueue)

    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=headers,
        json={"inputs": {"message": "cancel me"}},
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "pending"
    run_id = created.json()["id"]

    cancelled = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs/{run_id}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancel_requested_at"]

    retried = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs/{run_id}/retry",
        headers=headers,
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["status"] == "pending"
    assert retried.json()["retry_of_run_id"] == run_id
    assert retried.json()["id"] != run_id
    assert enqueue.await_count == 2

    async def claim_retry_once() -> tuple[bool, bool, str, int]:
        retried_run_id = retried.json()["id"]
        async with SessionLocal() as first_db:
            first = await claim_workflow_run(first_db, retried_run_id)
        async with SessionLocal() as second_db:
            duplicate = await claim_workflow_run(second_db, retried_run_id)
            stored = await second_db.get(WorkflowRun, retried_run_id)
            assert stored is not None
            return first is not None, duplicate is not None, stored.status, stored.attempt_count

    import asyncio

    claimed, claimed_twice, run_status, attempt_count = asyncio.run(claim_retry_once())
    assert claimed is True
    assert claimed_twice is False
    assert run_status == "running"
    assert attempt_count == 1


def test_worker_persists_cooperative_cancellation(client: TestClient, monkeypatch):
    session = register(client, "worker-cancel@example.com", "Worker Cancel")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "Worker cancellation"},
    ).json()
    monkeypatch.setattr(
        workflow_routes,
        "enqueue_persisted_workflow_run",
        AsyncMock(),
    )
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/run",
        headers=headers,
        json={"inputs": {}},
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["id"]
    monkeypatch.setattr(
        workflow_worker,
        "run_cancellation_requested",
        lambda requested_run_id: requested_run_id == run_id,
    )

    import asyncio

    assert asyncio.run(workflow_worker._execute_run(run_id)) == "cancelled"
    stored = client.get(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/runs/{run_id}",
        headers=headers,
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "cancelled"
    assert stored.json()["attempt_count"] == 1


def test_expired_files_are_removed_from_database_and_storage(client: TestClient):
    session = register(client, "file-lifecycle@example.com", "File Lifecycle")
    headers = auth(session)
    workspace_id = client.get("/api/v1/workspaces", headers=headers).json()[0]["id"]
    workflow = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        headers=headers,
        json={"name": "File lifecycle workflow"},
    ).json()
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow['id']}/files",
        headers=headers,
        files={"file": ("temporary.txt", b"temporary", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]

    async def expire_and_cleanup() -> tuple[dict[str, int], Path]:
        async with SessionLocal() as db:
            stored = await db.get(StoredFile, file_id)
            assert stored is not None
            path = TEST_STORAGE_PATH.joinpath(*stored.object_key.split("/"))
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        async with SessionLocal() as db:
            result = await cleanup_file_lifecycle(db)
        return result, path

    import asyncio

    cleanup, path = asyncio.run(expire_and_cleanup())
    assert cleanup["expired"] == 1
    assert not path.exists()

    async def file_exists() -> bool:
        async with SessionLocal() as db:
            return await db.get(StoredFile, file_id) is not None

    assert asyncio.run(file_exists()) is False
