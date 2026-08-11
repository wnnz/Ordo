from pathlib import Path
from typing import Any

PINGCODE_WORKLOG_TEMPLATE_ID = "pingcode-worklog-filler"
PINGCODE_WORKLOG_SLUG = "pingcode-worklog-filler"
PINGCODE_WORKLOG_NAME = "PingCode 工时补齐"
PINGCODE_WORKLOG_DESCRIPTION = (
    "按起始年月检查当前用户在 NEWDMS 迭代中的 Task，并补齐法定工作日工时。"
)
PINGCODE_WORKLOG_SOURCE = (
    Path(__file__).parents[1]
    .joinpath("script_sources", "pingcode_worklog_filler.py")
    .read_text(encoding="utf-8")
)

OPTIONAL_STRING: dict[str, Any] = {"type": ["string", "null"], "default": ""}

PINGCODE_WORKLOG_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "access_token": {
            **OPTIONAL_STRING,
            "description": "PingCode personal or enterprise access token",
        },
        "client_id": {
            **OPTIONAL_STRING,
            "description": "PingCode Open API application client ID",
        },
        "client_secret": {
            **OPTIONAL_STRING,
            "description": "PingCode Open API application client secret",
        },
        "project_identifier": {
            "type": "string",
            "default": "NEWDMS",
            "minLength": 1,
        },
        "project_id": OPTIONAL_STRING,
        "assignee_id": OPTIONAL_STRING,
        "assignee_email": {
            **OPTIONAL_STRING,
            "description": "Required for enterprise tokens; omitted for personal tokens",
        },
        "start_month": {
            "type": "string",
            "pattern": r"^\d{4}-(0[1-9]|1[0-2])$",
            "description": "First month to inspect, in YYYY-MM format",
        },
        "daily_hours": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": 24,
            "default": 8,
        },
        "dry_run": {
            "type": "boolean",
            "default": True,
            "description": "Preview planned worklogs without creating them",
        },
        "mode": {
            "type": "string",
            "enum": ["preview", "write"],
            "description": "Workflow-friendly alternative to dry_run",
        },
        "include_today": {"type": "boolean", "default": False},
        "workload_type_id": OPTIONAL_STRING,
        "workload_type_name": OPTIONAL_STRING,
        "preferred_title_keyword": {
            "type": "string",
            "default": "会议及其他",
        },
        "holiday_calendar_url_template": {
            "type": "string",
            "default": (
                "https://raw.githubusercontent.com/"
                "NateScarlet/holiday-cn/master/{year}.json"
            ),
        },
        "holiday_calendar_required": {"type": "boolean", "default": True},
        "holiday_dates": {
            "type": "array",
            "items": {"type": "string", "format": "date"},
            "default": [],
        },
        "workday_dates": {
            "type": "array",
            "items": {"type": "string", "format": "date"},
            "default": [],
        },
        "max_backfill_days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 3660,
            "default": 400,
        },
        "max_write_days": {
            "type": "integer",
            "minimum": 1,
            "maximum": 366,
            "default": 31,
        },
        "description_prefix": {
            "type": "string",
            "default": "Ordo worklog backfill",
            "maxLength": 200,
        },
        "api_root": {
            "type": "string",
            "default": "https://open.pingcode.com/v1",
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": 5,
            "maximum": 120,
            "default": 30,
        },
    },
    "required": ["start_month"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}

PINGCODE_WORKLOG_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dry_run": {"type": "boolean"},
        "auth_mode": {"type": "string"},
        "project": SUMMARY_SCHEMA,
        "assignee": SUMMARY_SCHEMA,
        "task_count": {"type": "integer"},
        "planned_days": {"type": "integer"},
        "planned_hours": {"type": "number"},
        "created_days": {"type": "integer"},
        "created_hours": {"type": "number"},
        "available_workload_types": {
            "type": "array",
            "items": SUMMARY_SCHEMA,
        },
        "entries": {
            "type": "array",
            "items": SUMMARY_SCHEMA,
        },
        "skipped": SUMMARY_SCHEMA,
    },
    "required": [
        "dry_run",
        "auth_mode",
        "project",
        "assignee",
        "task_count",
        "planned_days",
        "planned_hours",
        "created_days",
        "created_hours",
        "available_workload_types",
        "entries",
        "skipped",
    ],
    "additionalProperties": False,
}


def pingcode_worklog_template() -> dict[str, Any]:
    return {
        "id": PINGCODE_WORKLOG_TEMPLATE_ID,
        "name": PINGCODE_WORKLOG_NAME,
        "description": PINGCODE_WORKLOG_DESCRIPTION,
        "category": "automation",
        "source_files": {"main.py": PINGCODE_WORKLOG_SOURCE},
        "entrypoint": "main:main",
        "input_schema": PINGCODE_WORKLOG_INPUT_SCHEMA,
        "output_schema": PINGCODE_WORKLOG_OUTPUT_SCHEMA,
        "sample_inputs": {
            "access_token": "",
            "client_id": "",
            "client_secret": "",
            "project_identifier": "NEWDMS",
            "assignee_email": "",
            "start_month": "2026-01",
            "daily_hours": 8,
            "dry_run": True,
            "include_today": False,
            "workload_type_id": "",
            "preferred_title_keyword": "会议及其他",
        },
        "network_enabled": True,
    }
