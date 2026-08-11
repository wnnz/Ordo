from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://open.pingcode.com/v1"
CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_HOLIDAY_URL = (
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
)
KNOWN_NON_TASK_TYPES = {
    "bug",
    "epic",
    "feature",
    "issue",
    "plan",
    "requirement",
    "story",
}
TASK_MARKERS = {"task", "\u4efb\u52a1"}


def _text(value):
    return str(value or "").strip()


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "on"}


def _dry_run_mode(inputs):
    mode = _text(inputs.get("mode")).lower()
    if mode:
        if mode not in {"preview", "write"}:
            raise ValueError("mode must be preview or write")
        return mode == "preview"
    return _bool(inputs.get("dry_run"), True)


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _json_body(response):
    raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("PingCode returned an invalid JSON response") from exc


def _request_json(method, url, *, token="", body=None, timeout=30):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Ordo-PingCode-Worklog/1.0",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return _json_body(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(
            f"PingCode request failed: {method} {url.split('?', 1)[0]} "
            f"returned HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"PingCode request failed: {method} {url.split('?', 1)[0]}: {exc.reason}"
        ) from exc


def _values(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("values", "items", "results", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    nested = payload.get("data")
    if isinstance(nested, (dict, list)):
        return _values(nested)
    return []


def _total(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("total", "total_count", "count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    nested = payload.get("data")
    return _total(nested) if isinstance(nested, dict) else None


class PingCodeClient:
    def __init__(self, token, *, api_root=API_ROOT, timeout=30):
        self.token = token
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout

    def request(self, method, path, *, params=None, body=None):
        url = self.api_root + path
        if params:
            url += "?" + urlencode(params)
        return _request_json(
            method,
            url,
            token=self.token,
            body=body,
            timeout=self.timeout,
        )

    def get_all(self, path, *, params=None, page_size=100):
        collected = []
        seen_ids = set()
        base_params = dict(params or {})
        for page_index in range(100):
            payload = self.request(
                "GET",
                path,
                params={
                    **base_params,
                    "page_size": page_size,
                    "page_index": page_index,
                },
            )
            page = _values(payload)
            if not page:
                break
            added = 0
            for item in page:
                item_id = _text(item.get("id"))
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                collected.append(item)
                added += 1
            total = _total(payload)
            if total is not None and len(collected) >= total:
                break
            if len(page) < page_size or added == 0:
                break
        return collected

    def search_work_items(self, *, project_id, assignee_id, page_size=100):
        collected = []
        seen_ids = set()
        for page_index in range(100):
            payload = self.request(
                "POST",
                "/pjm/work_items/search",
                body={
                    "mode": "query",
                    "payload": {
                        "filter": {
                            "project.id": {"in": [project_id]},
                            "assignee.id": {"in": [assignee_id]},
                            "type": {"in": ["task"]},
                        },
                        "include_deleted": False,
                        "include_archived": False,
                        "page_size": page_size,
                        "page_index": page_index,
                    },
                },
            )
            page = _values(payload)
            if not page:
                break
            added = 0
            for item in page:
                item_id = _text(item.get("id"))
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                collected.append(item)
                added += 1
            total = _total(payload)
            if total is not None and len(collected) >= total:
                break
            if len(page) < page_size or added == 0:
                break
        return collected


def _access_token(inputs):
    direct = _text(inputs.get("access_token"))
    if direct:
        return direct, "access_token"
    client_id = _text(inputs.get("client_id"))
    client_secret = _text(inputs.get("client_secret"))
    if not client_id or not client_secret:
        raise ValueError(
            "Configure access_token, or both client_id and client_secret. "
            "A browser login session cannot be reused by this background workflow."
        )
    query = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )
    payload = _request_json(
        "GET",
        f"{API_ROOT}/auth/token?{query}",
        timeout=int(inputs.get("timeout_seconds", 30)),
    )
    token = _text(payload.get("access_token") if isinstance(payload, dict) else "")
    if not token:
        raise RuntimeError("PingCode token response did not include access_token")
    return token, "client_credentials"


def _resolve_project(client, identifier, explicit_id=""):
    if explicit_id:
        project = client.request("GET", f"/project/projects/{explicit_id}")
        if not isinstance(project, dict):
            raise RuntimeError("PingCode project response is invalid")
        if identifier and _text(project.get("identifier")).casefold() != identifier.casefold():
            raise ValueError("project_id does not match project_identifier")
        return project
    matches = [
        project
        for project in client.get_all("/project/projects")
        if _text(project.get("identifier")).casefold() == identifier.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one PingCode project with identifier {identifier!r}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _resolve_user(client, *, explicit_id="", email=""):
    if explicit_id:
        user = client.request("GET", f"/directory/users/{explicit_id}")
        if not isinstance(user, dict):
            raise RuntimeError("PingCode user response is invalid")
        return user
    if email:
        matches = [
            user
            for user in client.get_all("/directory/users")
            if _text(user.get("email")).casefold() == email.casefold()
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one PingCode user with email {email!r}; found {len(matches)}"
            )
        return matches[0]
    try:
        user = client.request("GET", "/myself")
    except RuntimeError as exc:
        raise ValueError(
            "An enterprise token has no current user. Configure assignee_id or "
            "assignee_email for the PingCode account whose Tasks should receive worklogs."
        ) from exc
    if not isinstance(user, dict) or not _text(user.get("id")):
        raise RuntimeError("PingCode current-user response is invalid")
    return user


def _nested_id(value):
    if isinstance(value, dict):
        return _text(value.get("id"))
    return _text(value)


def _project_id(item):
    return _text(item.get("project_id")) or _nested_id(item.get("project"))


def _assignee_ids(item):
    values = []
    direct = _text(item.get("assignee_id"))
    if direct:
        values.append(direct)
    assignee = item.get("assignee")
    if isinstance(assignee, list):
        values.extend(_nested_id(value) for value in assignee)
    elif assignee is not None:
        values.append(_nested_id(assignee))
    return {value for value in values if value}


def _type_markers(item):
    markers = set()
    for key in ("type", "type_id", "work_item_type", "work_item_type_id"):
        value = item.get(key)
        if isinstance(value, dict):
            for field in ("id", "identifier", "name", "group", "type"):
                marker = _text(value.get(field)).casefold()
                if marker:
                    markers.add(marker)
        else:
            marker = _text(value).casefold()
            if marker:
                markers.add(marker)
    return markers


def _is_task(item):
    markers = _type_markers(item)
    return bool(markers & TASK_MARKERS) and not bool(markers & KNOWN_NON_TASK_TYPES)


def _sprint_id(item):
    for key in ("sprint_id", "iteration_id"):
        value = _text(item.get(key))
        if value:
            return value
    for key in ("sprint", "iteration"):
        value = _nested_id(item.get(key))
        if value:
            return value
    return ""


def _as_local_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)) or _text(value).isdigit():
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, CHINA_TZ).date()
    raw = _text(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid PingCode date value: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ).date()


def _load_sprints(client, project_id):
    result = {}
    path = f"/project/projects/{project_id}/sprints"
    for sprint in client.get_all(path):
        sprint_id = _text(sprint.get("id"))
        start = _as_local_date(sprint.get("start_at"))
        end = _as_local_date(sprint.get("end_at"))
        if not sprint_id or not start or not end or end < start:
            continue
        result[sprint_id] = {
            "id": sprint_id,
            "name": _text(sprint.get("name")),
            "start": start,
            "end": end,
        }
    return result


def _filter_tasks(items, *, project_id, assignee_id, sprints):
    accepted = []
    skipped = {
        "not_task": 0,
        "wrong_project": 0,
        "wrong_assignee": 0,
        "no_iteration": 0,
    }
    for item in items:
        if not _is_task(item):
            skipped["not_task"] += 1
            continue
        if _project_id(item) != project_id:
            skipped["wrong_project"] += 1
            continue
        if _assignee_ids(item) != {assignee_id}:
            skipped["wrong_assignee"] += 1
            continue
        sprint_id = _sprint_id(item)
        if not sprint_id or sprint_id not in sprints:
            skipped["no_iteration"] += 1
            continue
        accepted.append({**item, "_sprint_id": sprint_id})
    return accepted, skipped


def _task_sort_key(item, preferred_keyword):
    title = _text(item.get("title"))
    return (
        0 if preferred_keyword and preferred_keyword.casefold() in title.casefold() else 1,
        _text(item.get("identifier")),
        _text(item.get("id")),
    )


def _tasks_by_sprint(tasks, preferred_keyword):
    grouped = {}
    for task in tasks:
        grouped.setdefault(task["_sprint_id"], []).append(task)
    for sprint_tasks in grouped.values():
        sprint_tasks.sort(key=lambda item: _task_sort_key(item, preferred_keyword))
    return grouped


def _holiday_calendar(start, end, *, url_template, required=True):
    explicit = {}
    for year in range(start.year, end.year + 1):
        if not url_template:
            if required:
                raise ValueError("holiday_calendar_url_template is required")
            continue
        url = url_template.format(year=year)
        try:
            payload = _request_json("GET", url, timeout=30)
        except RuntimeError:
            if required:
                raise
            continue
        if not isinstance(payload, dict) or int(payload.get("year", 0)) != year:
            if required:
                raise RuntimeError(f"Holiday calendar for {year} is invalid")
            continue
        for item in payload.get("days", []):
            if not isinstance(item, dict):
                continue
            try:
                day = date.fromisoformat(_text(item.get("date")))
            except ValueError:
                continue
            explicit[day] = bool(item.get("isOffDay"))
    return explicit


def _apply_calendar_overrides(calendar, holiday_dates, workday_dates):
    for value in holiday_dates or []:
        calendar[date.fromisoformat(_text(value))] = True
    for value in workday_dates or []:
        calendar[date.fromisoformat(_text(value))] = False
    return calendar


def _is_workday(day, calendar):
    if day in calendar:
        return not calendar[day]
    return day.weekday() < 5


def _day_timestamp(day, *, end=False):
    value = time(23, 59, 59) if end else time(0, 0)
    return int(datetime.combine(day, value, tzinfo=CHINA_TZ).timestamp())


def _date_chunks(start, end, days=85):
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _reporter_id(workload):
    return (
        _text(workload.get("report_by_id"))
        or _nested_id(workload.get("report_by"))
        or _nested_id(workload.get("reporter"))
    )


def _workload_hours_by_day(client, *, assignee_id, start, end):
    totals = {}
    for chunk_start, chunk_end in _date_chunks(start, end):
        workloads = client.get_all(
            "/workloads",
            params={
                "principal_type": "work_item",
                "start_at": _day_timestamp(chunk_start),
                "end_at": _day_timestamp(chunk_end, end=True),
            },
        )
        for workload in workloads:
            if _reporter_id(workload) != assignee_id:
                continue
            report_day = _as_local_date(workload.get("report_at"))
            if not report_day or report_day < start or report_day > end:
                continue
            duration = _decimal(workload.get("duration"))
            if duration > 0:
                totals[report_day] = totals.get(report_day, Decimal("0")) + duration
    return totals


def _available_workload_types(client):
    result = []
    for item in client.get_all("/workload_types"):
        item_id = _text(item.get("id"))
        if not item_id:
            continue
        result.append({"id": item_id, "name": _text(item.get("name"))})
    return result


def _resolve_workload_type(types, *, explicit_id="", name="", required=False):
    if explicit_id:
        if types and explicit_id not in {item["id"] for item in types}:
            raise ValueError("workload_type_id does not exist in PingCode")
        return explicit_id
    if name:
        matches = [item for item in types if item["name"].casefold() == name.casefold()]
        if len(matches) == 1:
            return matches[0]["id"]
        if required:
            raise ValueError(
                f"Expected exactly one PingCode workload type named {name!r}; found {len(matches)}"
            )
    if len(types) == 1:
        return types[0]["id"]
    if required:
        raise ValueError(
            "Configure workload_type_id (recommended) or an exact workload_type_name "
            "before disabling dry_run"
        )
    return ""


def _select_sprint(day, sprints, tasks_by_sprint):
    matches = [
        sprint
        for sprint_id, sprint in sprints.items()
        if sprint_id in tasks_by_sprint and sprint["start"] <= day <= sprint["end"]
    ]
    matches.sort(key=lambda sprint: (sprint["start"], sprint["end"], sprint["id"]), reverse=True)
    return matches[0] if matches else None


def _plan_entries(
    *,
    start,
    end,
    calendar,
    daily_hours,
    existing_hours,
    sprints,
    tasks_by_sprint,
):
    entries = []
    day = start
    while day <= end:
        if _is_workday(day, calendar):
            sprint = _select_sprint(day, sprints, tasks_by_sprint)
            worked = existing_hours.get(day, Decimal("0"))
            missing = max(Decimal("0"), daily_hours - worked)
            if sprint and missing > 0:
                task = tasks_by_sprint[sprint["id"]][0]
                entries.append(
                    {
                        "date": day.isoformat(),
                        "existing_hours": float(worked),
                        "hours": float(missing),
                        "task_id": _text(task.get("id")),
                        "task_identifier": _text(task.get("identifier")),
                        "task_title": _text(task.get("title")),
                        "sprint_id": sprint["id"],
                        "sprint_name": sprint["name"],
                        "status": "planned",
                    }
                )
        day += timedelta(days=1)
    return entries


def _create_workloads(
    client,
    *,
    entries,
    assignee_id,
    workload_type_id,
    description_prefix,
):
    created = []
    for entry in entries:
        report_day = date.fromisoformat(entry["date"])
        payload = client.request(
            "POST",
            "/workloads",
            body={
                "principal_id": entry["task_id"],
                "principal_type": "work_item",
                "type_id": workload_type_id,
                "duration": entry["hours"],
                "report_at": int(
                    datetime.combine(report_day, time(12, 0), tzinfo=CHINA_TZ).timestamp()
                ),
                "report_by_id": assignee_id,
                "description": f"{description_prefix} {entry['date']}",
            },
        )
        created.append(
            {
                **entry,
                "status": "created",
                "workload_id": _text(payload.get("id")) if isinstance(payload, dict) else "",
            }
        )
    return created


def main(inputs, context):
    if not context.get("network_enabled"):
        raise ValueError("Enable network access for this script version before running it")

    start_month = _text(inputs.get("start_month"))
    try:
        start = datetime.strptime(start_month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ValueError("start_month must use YYYY-MM") from exc

    include_today = _bool(inputs.get("include_today"), False)
    end = datetime.now(CHINA_TZ).date() - (timedelta(0) if include_today else timedelta(days=1))
    if start > end:
        return {
            "dry_run": _dry_run_mode(inputs),
            "auth_mode": "not_requested",
            "project": {},
            "assignee": {},
            "task_count": 0,
            "planned_days": 0,
            "planned_hours": 0,
            "created_days": 0,
            "created_hours": 0,
            "available_workload_types": [],
            "entries": [],
            "skipped": {},
        }
    max_backfill_days = int(inputs.get("max_backfill_days", 400))
    if (end - start).days + 1 > max_backfill_days:
        raise ValueError(
            f"Requested range exceeds max_backfill_days={max_backfill_days}; choose a later start month"
        )

    daily_hours = _decimal(inputs.get("daily_hours", 8))
    if daily_hours <= 0 or daily_hours > 24:
        raise ValueError("daily_hours must be greater than 0 and no more than 24")
    dry_run = _dry_run_mode(inputs)

    token, auth_mode = _access_token(inputs)
    client = PingCodeClient(
        token,
        api_root=_text(inputs.get("api_root")) or API_ROOT,
        timeout=int(inputs.get("timeout_seconds", 30)),
    )
    project_identifier = _text(inputs.get("project_identifier")) or "NEWDMS"
    project = _resolve_project(
        client,
        project_identifier,
        explicit_id=_text(inputs.get("project_id")),
    )
    project_id = _text(project.get("id"))
    assignee = _resolve_user(
        client,
        explicit_id=_text(inputs.get("assignee_id")),
        email=_text(inputs.get("assignee_email")),
    )
    assignee_id = _text(assignee.get("id"))

    sprints = _load_sprints(client, project_id)
    raw_items = client.search_work_items(project_id=project_id, assignee_id=assignee_id)
    tasks, skipped = _filter_tasks(
        raw_items,
        project_id=project_id,
        assignee_id=assignee_id,
        sprints=sprints,
    )
    preferred_keyword = _text(inputs.get("preferred_title_keyword")) or "\u4f1a\u8bae\u53ca\u5176\u4ed6"
    tasks_by_sprint = _tasks_by_sprint(tasks, preferred_keyword)

    calendar = _holiday_calendar(
        start,
        end,
        url_template=_text(inputs.get("holiday_calendar_url_template")) or DEFAULT_HOLIDAY_URL,
        required=_bool(inputs.get("holiday_calendar_required"), True),
    )
    _apply_calendar_overrides(
        calendar,
        inputs.get("holiday_dates", []),
        inputs.get("workday_dates", []),
    )
    existing_hours = _workload_hours_by_day(
        client,
        assignee_id=assignee_id,
        start=start,
        end=end,
    )
    entries = _plan_entries(
        start=start,
        end=end,
        calendar=calendar,
        daily_hours=daily_hours,
        existing_hours=existing_hours,
        sprints=sprints,
        tasks_by_sprint=tasks_by_sprint,
    )

    workload_types = _available_workload_types(client)
    workload_type_id = _resolve_workload_type(
        workload_types,
        explicit_id=_text(inputs.get("workload_type_id")),
        name=_text(inputs.get("workload_type_name")),
        required=not dry_run and bool(entries),
    )
    if not dry_run and len(entries) > int(inputs.get("max_write_days", 31)):
        raise ValueError(
            "Planned write count exceeds max_write_days; run a smaller range or raise the guard explicitly"
        )

    final_entries = entries
    if not dry_run and entries:
        final_entries = _create_workloads(
            client,
            entries=entries,
            assignee_id=assignee_id,
            workload_type_id=workload_type_id,
            description_prefix=_text(inputs.get("description_prefix")) or "Ordo worklog backfill",
        )

    planned_hours = sum(_decimal(entry["hours"]) for entry in entries)
    created_entries = [entry for entry in final_entries if entry["status"] == "created"]
    created_hours = sum(_decimal(entry["hours"]) for entry in created_entries)
    return {
        "dry_run": dry_run,
        "auth_mode": auth_mode,
        "project": {
            "id": project_id,
            "identifier": _text(project.get("identifier")),
            "name": _text(project.get("name")),
        },
        "assignee": {
            "id": assignee_id,
            "email": _text(assignee.get("email")),
            "display_name": _text(assignee.get("display_name")) or _text(assignee.get("name")),
        },
        "task_count": len(tasks),
        "planned_days": len(entries),
        "planned_hours": float(planned_hours),
        "created_days": len(created_entries),
        "created_hours": float(created_hours),
        "available_workload_types": workload_types,
        "entries": final_entries,
        "skipped": skipped,
    }
