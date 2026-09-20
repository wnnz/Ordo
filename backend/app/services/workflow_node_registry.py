import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from fastapi import HTTPException, status

from app.services.host_info import execute_host_info_node
from app.services.rdp_disconnect import execute_rdp_disconnect_node
from app.services.workflow_values import (
    coerce_assignment_value,
    empty_assignment_value,
    evaluate_classifier,
    evaluate_condition,
    first_non_null,
    list_item_matches,
    read_object_path,
    sortable_value,
    stable_item_key,
)

NodeExecutor = Callable[[dict[str, Any], dict[str, Any]], Any]


def execute_start(config: dict[str, Any], context: dict[str, Any]) -> Any:
    return deepcopy(context.get("inputs", {}))


def execute_end(config: dict[str, Any], context: dict[str, Any]) -> Any:
    outputs = config.get("outputs", context)
    if isinstance(outputs, list):
        return {str(output["name"]): output.get("value") for output in outputs}
    return outputs


def execute_variable(config: dict[str, Any], context: dict[str, Any]) -> Any:
    if not isinstance(config.get("assignments"), list):
        return config.get("values", {})
    result = deepcopy(config.get("values", {})) if isinstance(config.get("values"), dict) else {}
    for assignment in config["assignments"]:
        name = str(assignment.get("name", ""))
        operation = assignment.get("operation", "overwrite")
        value = coerce_assignment_value(assignment.get("value"), assignment.get("type", "Any"))
        if operation == "clear":
            result[name] = empty_assignment_value(assignment.get("type", "Any"))
        elif operation == "append":
            current = result.get(name, "")
            result[name] = [*current, value] if isinstance(current, list) else f"{current}{value}"
        elif operation == "extend":
            current = result.get(name, [])
            addition = value if isinstance(value, list) else [value]
            result[name] = [*(current if isinstance(current, list) else [current]), *addition]
        else:
            result[name] = value
    return result


def execute_json(config: dict[str, Any], context: dict[str, Any]) -> Any:
    raw = config.get("value", {})
    return json.loads(raw) if isinstance(raw, str) else raw


def execute_aggregate(config: dict[str, Any], context: dict[str, Any]) -> Any:
    if config.get("group_enabled", False):
        grouped = {
            group["name"]: first_non_null(group.get("variables", []))
            for group in config.get("groups", [])
        }
        return {**grouped, "output": grouped}
    values = config.get("variables", [])
    return {"output": first_non_null(values), "values": values}


def execute_wait(config: dict[str, Any], context: dict[str, Any]) -> Any:
    return {"completed": True, "mode": config.get("mode", "all")}


def execute_list(config: dict[str, Any], context: dict[str, Any]) -> Any:
    source = config.get("source", [])
    if not isinstance(source, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "List node source must be an array"
        )
    operation = config.get("operation", "filter")
    if any(key in config for key in ("filter", "nth", "limit", "sort", "unique")):
        items = list(source)
        filter_config = config.get("filter", {})
        if filter_config.get("enabled"):
            items = [item for item in items if list_item_matches(item, filter_config)]
        if config.get("sort", {}).get("enabled"):
            sort_config = config["sort"]
            key_name = str(sort_config.get("key", "")).strip()
            items = sorted(
                items,
                key=lambda item: sortable_value(
                    read_object_path(item, key_name) if key_name else item
                ),
                reverse=sort_config.get("order") == "desc",
            )
        if config.get("unique"):
            seen: set[str] = set()
            items = [
                item
                for item in items
                if not (stable_item_key(item) in seen or seen.add(stable_item_key(item)))
            ]
        if config.get("limit", {}).get("enabled"):
            items = items[: int(config["limit"].get("count", 10))]
        item = None
        if config.get("nth", {}).get("enabled"):
            index = int(config["nth"].get("index", 1)) - 1
            item = items[index] if 0 <= index < len(items) else None
        return {"items": items, "item": item}
    if operation == "unique":
        seen = set()
        return {
            "items": [
                item
                for item in source
                if not (stable_item_key(item) in seen or seen.add(stable_item_key(item)))
            ],
            "item": None,
        }
    if operation == "sort":
        return {"items": sorted(source, key=sortable_value), "item": None}
    if operation == "slice":
        return {
            "items": source[int(config.get("start", 0)) : int(config.get("end", len(source)))],
            "item": None,
        }
    return {"items": source, "item": None}


def execute_condition_node(config: dict[str, Any], context: dict[str, Any]) -> Any:
    return evaluate_condition(config)


def execute_classifier_node(config: dict[str, Any], context: dict[str, Any]) -> Any:
    return evaluate_classifier(config)


NODE_EXECUTORS: dict[str, NodeExecutor] = {
    "start": execute_start,
    "end": execute_end,
    "variable": execute_variable,
    "json": execute_json,
    "aggregate": execute_aggregate,
    "wait": execute_wait,
    "list": execute_list,
    "condition": execute_condition_node,
    "classifier": execute_classifier_node,
    "host_info": execute_host_info_node,
    "rdp_disconnect": execute_rdp_disconnect_node,
}


def execute_registered_node(
    node_type: str, config: dict[str, Any], context: dict[str, Any]
) -> tuple[bool, Any]:
    executor = NODE_EXECUTORS.get(node_type)
    if not executor:
        return False, None
    return True, executor(config, context)
