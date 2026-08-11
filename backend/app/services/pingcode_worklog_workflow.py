from __future__ import annotations

from typing import Any

from app.services.pingcode_worklog_script import (
    PINGCODE_WORKLOG_INPUT_SCHEMA,
    PINGCODE_WORKLOG_NAME,
    PINGCODE_WORKLOG_OUTPUT_SCHEMA,
)

PINGCODE_WORKLOG_WORKFLOW_TEMPLATE_ID = "pingcode_worklog"

PINGCODE_ENVIRONMENT_VARIABLES = [
    (
        "PINGCODE_ACCESS_TOKEN",
        "secret",
        "Optional personal or enterprise token. Leave empty when using client credentials.",
    ),
    (
        "PINGCODE_CLIENT_ID",
        "secret",
        "PingCode Open API application client ID.",
    ),
    (
        "PINGCODE_CLIENT_SECRET",
        "secret",
        "PingCode Open API application client secret.",
    ),
    (
        "PINGCODE_ASSIGNEE_ID",
        "string",
        "Optional exact PingCode user ID for enterprise-token runs.",
    ),
    (
        "PINGCODE_ASSIGNEE_EMAIL",
        "string",
        "PingCode email used to resolve the current user for enterprise-token runs.",
    ),
    (
        "PINGCODE_WORKLOAD_TYPE_ID",
        "string",
        "Required before write mode unless the enterprise has exactly one workload type.",
    ),
]


def build_pingcode_worklog_graph(
    *,
    script_id: str,
    script_version: int | str = "latest",
) -> dict[str, Any]:
    policy = {
        "retry": {"enabled": False, "max_retries": 3, "interval_seconds": 0},
        "error_strategy": "fail",
        "default_output": {},
    }
    nodes = [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 80, "y": 180},
            "data": {
                "label": "工时范围",
                "config": {
                    "triggers": ["form"],
                    "input_fields": [
                        {
                            "name": "start_month",
                            "label": "起始年月",
                            "type": "month",
                            "required": True,
                            "placeholder": "",
                            "default_value": "",
                            "max_length": None,
                        },
                        {
                            "name": "mode",
                            "label": "执行模式",
                            "type": "select",
                            "required": True,
                            "options": ["preview", "write"],
                            "default_value": "preview",
                            "placeholder": "",
                            "max_length": None,
                        },
                        {
                            "name": "daily_hours",
                            "label": "每日目标工时",
                            "type": "number",
                            "required": True,
                            "default_value": 8,
                            "min": 0.25,
                            "max": 24,
                            "max_length": None,
                        },
                    ],
                    "schedule": {
                        "cron": "0 18 * * 1-5",
                        "timezone": "Asia/Shanghai",
                        "enabled": False,
                        "inputs_json": "{}",
                    },
                },
            },
        },
        {
            "id": "fill-worklogs",
            "type": "script",
            "position": {"x": 430, "y": 180},
            "data": {
                "label": "补齐 PingCode 工时",
                "description": "只核验并处理 NEWDMS 中当前用户负责的 Task",
                "config": {
                    "script_id": script_id,
                    "script_name": PINGCODE_WORKLOG_NAME,
                    "version": script_version,
                    "inputs": {
                        "access_token": "{{env.PINGCODE_ACCESS_TOKEN}}",
                        "client_id": "{{env.PINGCODE_CLIENT_ID}}",
                        "client_secret": "{{env.PINGCODE_CLIENT_SECRET}}",
                        "project_identifier": "NEWDMS",
                        "project_id": "",
                        "assignee_id": "{{env.PINGCODE_ASSIGNEE_ID}}",
                        "assignee_email": "{{env.PINGCODE_ASSIGNEE_EMAIL}}",
                        "start_month": "{{inputs.start_month}}",
                        "daily_hours": "{{inputs.daily_hours}}",
                        "mode": "{{inputs.mode}}",
                        "dry_run": True,
                        "include_today": False,
                        "workload_type_id": "{{env.PINGCODE_WORKLOAD_TYPE_ID}}",
                        "workload_type_name": "",
                        "preferred_title_keyword": "会议及其他",
                        "holiday_calendar_url_template": (
                            "https://raw.githubusercontent.com/"
                            "NateScarlet/holiday-cn/master/{year}.json"
                        ),
                        "holiday_calendar_required": True,
                        "holiday_dates": [],
                        "workday_dates": [],
                        "max_backfill_days": 400,
                        "max_write_days": 31,
                        "description_prefix": "Ordo worklog backfill",
                        "api_root": "https://open.pingcode.com/v1",
                        "timeout_seconds": 30,
                    },
                    "input_schema": PINGCODE_WORKLOG_INPUT_SCHEMA,
                    "output_schema": PINGCODE_WORKLOG_OUTPUT_SCHEMA,
                    **policy,
                },
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 780, "y": 180},
            "data": {
                "label": "结果",
                "config": {
                    "outputs": [
                        {
                            "name": "dry_run",
                            "type": "Boolean",
                            "value": "{{补齐 PingCode 工时.dry_run}}",
                        },
                        {
                            "name": "task_count",
                            "type": "Number",
                            "value": "{{补齐 PingCode 工时.task_count}}",
                        },
                        {
                            "name": "planned_days",
                            "type": "Number",
                            "value": "{{补齐 PingCode 工时.planned_days}}",
                        },
                        {
                            "name": "planned_hours",
                            "type": "Number",
                            "value": "{{补齐 PingCode 工时.planned_hours}}",
                        },
                        {
                            "name": "created_days",
                            "type": "Number",
                            "value": "{{补齐 PingCode 工时.created_days}}",
                        },
                        {
                            "name": "created_hours",
                            "type": "Number",
                            "value": "{{补齐 PingCode 工时.created_hours}}",
                        },
                        {
                            "name": "entries",
                            "type": "Array",
                            "value": "{{补齐 PingCode 工时.entries}}",
                        },
                        {
                            "name": "available_workload_types",
                            "type": "Array",
                            "value": "{{补齐 PingCode 工时.available_workload_types}}",
                        },
                        {
                            "name": "skipped",
                            "type": "Object",
                            "value": "{{补齐 PingCode 工时.skipped}}",
                        },
                    ]
                },
            },
        },
    ]
    edges = [
        {"id": "start-fill-worklogs", "source": "start", "target": "fill-worklogs"},
        {"id": "fill-worklogs-end", "source": "fill-worklogs", "target": "end"},
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges}
