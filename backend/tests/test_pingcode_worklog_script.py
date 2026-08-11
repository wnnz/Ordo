from datetime import date
from decimal import Decimal

from app.script_sources import pingcode_worklog_filler as worklog


def sprint(sprint_id="sprint-1"):
    return {
        sprint_id: {
            "id": sprint_id,
            "name": "Sprint 1",
            "start": date(2026, 1, 1),
            "end": date(2026, 1, 31),
        }
    }


def task(
    item_id,
    *,
    item_type="task",
    assignee_id="user-1",
    project_id="project-1",
    sprint_id="sprint-1",
    title="Implementation",
):
    return {
        "id": item_id,
        "identifier": f"NEWDMS-{item_id}",
        "title": title,
        "type": item_type,
        "assignee": {"id": assignee_id},
        "project": {"id": project_id},
        "sprint": {"id": sprint_id},
    }


def test_task_filter_fails_closed_for_story_wrong_owner_and_missing_type():
    items = [
        task("1"),
        task("2", item_type="story"),
        task("3", assignee_id="user-2"),
        task("4", sprint_id="missing"),
        {**task("5"), "type": None},
    ]

    accepted, skipped = worklog._filter_tasks(
        items,
        project_id="project-1",
        assignee_id="user-1",
        sprints=sprint(),
    )

    assert [item["id"] for item in accepted] == ["1"]
    assert skipped == {
        "not_task": 2,
        "wrong_project": 0,
        "wrong_assignee": 1,
        "no_iteration": 1,
    }


def test_task_filter_accepts_configured_task_group_but_rejects_conflicts():
    configured_task = {
        **task("1"),
        "type": None,
        "work_item_type": {"id": "custom-id", "name": "任务", "group": "task"},
    }
    conflicting = {
        **task("2"),
        "work_item_type": {"name": "任务", "group": "task"},
        "type": "story",
    }

    accepted, skipped = worklog._filter_tasks(
        [configured_task, conflicting],
        project_id="project-1",
        assignee_id="user-1",
        sprints=sprint(),
    )

    assert [item["id"] for item in accepted] == ["1"]
    assert skipped["not_task"] == 1


def test_plan_uses_preferred_task_and_respects_holiday_and_makeup_workday():
    tasks = [
        {**task("2", title="Regular task"), "_sprint_id": "sprint-1"},
        {**task("1", title="Sprint 1 会议及其他"), "_sprint_id": "sprint-1"},
    ]
    grouped = worklog._tasks_by_sprint(tasks, "会议及其他")
    calendar = {
        date(2026, 1, 2): True,
        date(2026, 1, 3): False,
    }

    entries = worklog._plan_entries(
        start=date(2026, 1, 1),
        end=date(2026, 1, 4),
        calendar=calendar,
        daily_hours=Decimal("8"),
        existing_hours={date(2026, 1, 1): Decimal("3")},
        sprints=sprint(),
        tasks_by_sprint=grouped,
    )

    assert [(entry["date"], entry["hours"]) for entry in entries] == [
        ("2026-01-01", 5.0),
        ("2026-01-03", 8.0),
    ]
    assert {entry["task_id"] for entry in entries} == {"1"}


def test_create_workloads_writes_only_the_selected_task():
    calls = []

    class Client:
        def request(self, method, path, *, body=None, params=None):
            calls.append((method, path, body, params))
            return {"id": "workload-1"}

    entries = [
        {
            "date": "2026-01-05",
            "existing_hours": 2,
            "hours": 6,
            "task_id": "task-1",
            "task_identifier": "NEWDMS-1",
            "task_title": "Task",
            "sprint_id": "sprint-1",
            "sprint_name": "Sprint 1",
            "status": "planned",
        }
    ]

    created = worklog._create_workloads(
        Client(),
        entries=entries,
        assignee_id="user-1",
        workload_type_id="type-1",
        description_prefix="Ordo",
    )

    assert created[0]["status"] == "created"
    assert created[0]["workload_id"] == "workload-1"
    assert calls[0][0:2] == ("POST", "/workloads")
    assert calls[0][2]["principal_id"] == "task-1"
    assert calls[0][2]["principal_type"] == "work_item"
    assert calls[0][2]["report_by_id"] == "user-1"
    assert calls[0][2]["duration"] == 6
