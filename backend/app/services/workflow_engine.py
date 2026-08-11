from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for_futures
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import PurePosixPath
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from croniter import croniter
from fastapi import HTTPException, status
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from app.core.config import get_settings
from app.services.answer_filling import fill_docx_answers
from app.services.document_processing import execute_document
from app.services.model_execution import (
    execute_agent,
    execute_extractor,
    execute_image_generation,
    execute_llm,
)
from app.services.sandbox_artifacts import consume_sandbox_artifacts, sandbox_schema_value
from app.services.scripts import validate_inputs, validate_script
from app.services.workflow_node_registry import execute_registered_node
from app.services.workflow_values import (
    coerce_assignment_value,
    extract_structured_parameters,
)

VARIABLE = re.compile(r"\{\{\s*([^{}\r\n]+?)\s*\}\}")
EXECUTION_POLICY_NODE_TYPES = {
    "llm", "image", "agent", "code", "script", "template", "variable", "json", "aggregate",
    "extract", "list", "http", "iteration", "loop",
    "delay", "subworkflow", "document", "answer_filler",
}
SUPPORTED_NODE_TYPES = {
    "start", "end", "note", "llm", "image", "agent", "classifier", "code",
    "script", "template", "variable", "json", "aggregate", "extract", "list",
    "http", "condition", "human", "wait", "iteration", "loop", "delay",
    "subworkflow", "document", "answer_filler", "host_info",
}


class WorkflowPause(Exception):
    def __init__(self, node_id: str, request: dict[str, Any], resume_state: dict[str, Any]):
        super().__init__(f"Workflow is waiting at node {node_id}")
        self.node_id = node_id
        self.request = request
        self.resume_state = resume_state


class WorkflowCancelled(Exception):
    pass


def validate_supported_node_types(nodes: list[dict[str, Any]]) -> None:
    for node in nodes:
        node_type = node.get("type")
        if node_type == "knowledge":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Knowledge nodes are no longer supported",
            )
        if node_type not in SUPPORTED_NODE_TYPES:
            label = str(node_type) if node_type else "<missing>"
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Unsupported node type: {label}",
            )


def node_reference_name(node: dict[str, Any]) -> str:
    return str(node.get("data", {}).get("label") or "").strip()


def validate_node_names(nodes: list[dict[str, Any]]) -> None:
    names: set[str] = set()
    for node in nodes:
        name = node_reference_name(node)
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Every node requires a name")
        if any(character in name for character in ".{}"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Node names cannot contain '.', '{', or '}'")
        key = name.casefold()
        if key in {"inputs", "env", "sys"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Node name is reserved")
        if key in names:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires unique node names")
        names.add(key)


def store_node_output(context: dict[str, Any], node: dict[str, Any], output: Any, graph: dict[str, Any]) -> None:
    context[str(node["id"])] = output
    name = node_reference_name(node)
    if name and sum(node_reference_name(item).casefold() == name.casefold() for item in graph.get("nodes", [])) == 1:
        context[name] = output


def validate_draft_graph(graph: dict[str, Any]) -> None:
    """Validate graph integrity without rejecting intentionally incomplete draft nodes."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph nodes and edges must be arrays")
    node_ids = [node.get("id") for node in nodes]
    if not node_ids or None in node_ids or len(set(node_ids)) != len(node_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires unique node ids")
    validate_supported_node_types(nodes)
    validate_node_names(nodes)
    top_level_nodes = [node for node in nodes if not node.get("parentNode")]
    if len([node for node in top_level_nodes if node.get("type") == "start"]) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires exactly one start node")
    if not any(node.get("type") == "end" for node in top_level_nodes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires an end node")
    validate_start_config(next(node for node in top_level_nodes if node.get("type") == "start").get("data", {}).get("config", {}))
    for end_node in (node for node in top_level_nodes if node.get("type") == "end"):
        validate_end_config(end_node.get("data", {}).get("config", {}))
    node_types = {node.get("id"): node.get("type") for node in nodes}
    node_parents = {node.get("id"): node.get("parentNode") for node in nodes}
    for node in nodes:
        parent_id = node.get("parentNode")
        if parent_id and node_types.get(parent_id) not in {"iteration", "loop"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nested nodes require an iteration or loop parent")
        if parent_id and node.get("type") in {"start", "end", "human", "iteration", "loop", "note"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported nested node type")
    for edge in edges:
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Edge references an unknown node")
        if node_types.get(edge.get("source")) == "note" or node_types.get(edge.get("target")) == "note":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Annotations cannot be connected")
        if node_parents.get(edge.get("source")) != node_parents.get(edge.get("target")):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Edges cannot cross a container boundary")
def validate_graph(graph: dict[str, Any]) -> None:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph nodes and edges must be arrays"
        )
    node_ids = [node.get("id") for node in nodes]
    if not node_ids or None in node_ids or len(set(node_ids)) != len(node_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires unique node ids")
    validate_supported_node_types(nodes)
    top_level_nodes = [node for node in nodes if not node.get("parentNode")]
    if not any(node.get("type") == "start" for node in top_level_nodes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires a start node")
    if not any(node.get("type") == "end" for node in top_level_nodes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires an end node")
    start_nodes = [node for node in top_level_nodes if node.get("type") == "start"]
    if len(start_nodes) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph requires exactly one start node")
    validate_start_config(start_nodes[0].get("data", {}).get("config", {}))
    for end_node in (node for node in top_level_nodes if node.get("type") == "end"):
        validate_end_config(end_node.get("data", {}).get("config", {}))
    for condition_node in (node for node in nodes if node.get("type") == "condition"):
        validate_condition_config(condition_node.get("data", {}).get("config", {}))
    for classifier_node in (node for node in nodes if node.get("type") == "classifier"):
        validate_classifier_config(classifier_node.get("data", {}).get("config", {}))
    for code_node in (node for node in nodes if node.get("type") == "code"):
        validate_code_config(code_node.get("data", {}).get("config", {}))
    for llm_node in (node for node in nodes if node.get("type") == "llm"):
        validate_llm_config(llm_node.get("data", {}).get("config", {}))
    for image_node in (node for node in nodes if node.get("type") == "image"):
        validate_image_config(image_node.get("data", {}).get("config", {}))
    for http_node in (node for node in nodes if node.get("type") == "http"):
        validate_http_config(http_node.get("data", {}).get("config", {}))
    for document_node in (node for node in nodes if node.get("type") == "document"):
        validate_document_config(document_node.get("data", {}).get("config", {}))
    for answer_filler_node in (node for node in nodes if node.get("type") == "answer_filler"):
        validate_answer_filler_config(answer_filler_node.get("data", {}).get("config", {}))
    for template_node in (node for node in nodes if node.get("type") == "template"):
        validate_template_config(template_node.get("data", {}).get("config", {}))
    for aggregate_node in (node for node in nodes if node.get("type") == "aggregate"):
        validate_aggregate_config(aggregate_node.get("data", {}).get("config", {}))
    for variable_node in (node for node in nodes if node.get("type") == "variable"):
        validate_variable_config(variable_node.get("data", {}).get("config", {}))
    for extract_node in (node for node in nodes if node.get("type") == "extract"):
        validate_extract_config(extract_node.get("data", {}).get("config", {}))
    for list_node in (node for node in nodes if node.get("type") == "list"):
        validate_list_config(list_node.get("data", {}).get("config", {}))
    for human_node in (node for node in nodes if node.get("type") == "human"):
        validate_human_config(human_node.get("data", {}).get("config", {}))
    for subworkflow_node in (node for node in nodes if node.get("type") == "subworkflow"):
        validate_subworkflow_config(subworkflow_node.get("data", {}).get("config", {}))
    for iteration_node in (node for node in nodes if node.get("type") == "iteration"):
        validate_iteration_config(iteration_node.get("data", {}).get("config", {}))
    for loop_node in (node for node in nodes if node.get("type") == "loop"):
        validate_loop_config(loop_node.get("data", {}).get("config", {}))
    for wait_node in (node for node in nodes if node.get("type") == "wait"):
        validate_wait_config(wait_node.get("data", {}).get("config", {}))
    for delay_node in (node for node in nodes if node.get("type") == "delay"):
        validate_delay_config(delay_node.get("data", {}).get("config", {}))
    for policy_node in (node for node in nodes if node.get("type") in EXECUTION_POLICY_NODE_TYPES):
        validate_execution_policy(policy_node.get("data", {}).get("config", {}))
    node_types = {node.get("id"): node.get("type") for node in nodes}
    node_parents = {node.get("id"): node.get("parentNode") for node in nodes}
    for node in nodes:
        parent_id = node.get("parentNode")
        if parent_id and node_types.get(parent_id) not in {"iteration", "loop"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nested nodes require an iteration or loop parent")
        if parent_id and node.get("type") in {"start", "end", "human", "iteration", "loop", "note"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported nested node type")
    for container in (node for node in nodes if node.get("type") in {"iteration", "loop"}):
        if not any(node.get("parentNode") == container.get("id") for node in nodes):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Containers require at least one child node")
    for edge in edges:
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Edge references an unknown node"
            )
        if node_types.get(edge.get("source")) == "note" or node_types.get(edge.get("target")) == "note":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Annotations cannot be connected"
            )
        if node_parents.get(edge.get("source")) != node_parents.get(edge.get("target")):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Edges cannot cross a container boundary")
    for wait_node in (node for node in nodes if node.get("type") == "wait"):
        if len([edge for edge in edges if edge.get("target") == wait_node.get("id")]) < 2:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Wait nodes require at least two incoming branches")
    for classifier_node in (node for node in nodes if node.get("type") == "classifier"):
        category_handles = {
            f"category:{category['id']}"
            for category in classifier_node.get("data", {}).get("config", {}).get("categories", [])
        }
        connected_handles = {
            str(edge.get("sourceHandle") or "")
            for edge in edges
            if edge.get("source") == classifier_node.get("id")
        }
        if not category_handles <= connected_handles:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Every classifier category requires a connected branch",
            )
        if connected_handles - category_handles:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Classifier contains an unknown category branch",
            )
    for human_node in (node for node in nodes if node.get("type") == "human"):
        action_handles = {
            f"action:{action['id']}"
            for action in normalized_human_actions(human_node.get("data", {}).get("config", {}))
        }
        connected_handles = {
            str(edge.get("sourceHandle") or "")
            for edge in edges
            if edge.get("source") == human_node.get("id")
        }
        connected_actions = {handle for handle in connected_handles if handle.startswith("action:")}
        if connected_actions and action_handles != connected_actions:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Every human action requires a connected branch",
            )
    for policy_node in (node for node in nodes if node.get("type") in EXECUTION_POLICY_NODE_TYPES):
        config = policy_node.get("data", {}).get("config", {})
        error_edges = [
            edge for edge in edges
            if edge.get("source") == policy_node.get("id") and edge.get("sourceHandle") == "error"
        ]
        if config.get("error_strategy", "fail") == "error_branch" and not error_edges:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Error branch strategy requires a connected error branch",
            )
        if config.get("error_strategy", "fail") != "error_branch" and error_edges:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Error branch is connected but the node does not use the error branch strategy",
            )


def validate_subworkflow_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("workflow_id"), str) or not config["workflow_id"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sub-workflow is required")
    if not isinstance(config.get("inputs", {}), dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Sub-workflow inputs must be an object")
    resolved_graph = config.get("_resolved_graph")
    if resolved_graph is not None and not isinstance(resolved_graph, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid resolved sub-workflow")


def validate_start_config(config: dict[str, Any]) -> None:
    triggers = config.get("triggers", ["form", "api"])
    allowed_triggers = {"form", "api", "webhook", "schedule"}
    if not isinstance(triggers, list) or len(triggers) != 1 or not set(triggers) <= allowed_triggers:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid start triggers")
    fields = config.get("input_fields", [])
    allowed_types = {"text", "textarea", "number", "month", "select", "file", "files"}
    names: list[str] = []
    for field in fields:
        name = str(field.get("name", ""))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid input field name")
        if field.get("type", "text") not in allowed_types:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid input field type")
        if field.get("type") == "select":
            options = field.get("options", [])
            if (
                not isinstance(options, list)
                or not options
                or any(not isinstance(option, str) or not option.strip() for option in options)
                or len(options) != len(set(options))
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Select field options must be unique and non-empty"
                )
            if field.get("default_value") not in (None, "") and field["default_value"] not in options:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Select field default must be one of its options"
                )
        max_length = field.get("max_length")
        if max_length is not None and (
            not isinstance(max_length, int) or max_length < 1 or max_length > 100_000
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid input field max length")
        if field.get("type") == "number":
            minimum, maximum = field.get("min"), field.get("max")
            if minimum is not None and not isinstance(minimum, (int, float)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid number field minimum")
            if maximum is not None and not isinstance(maximum, (int, float)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid number field maximum")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Number field minimum exceeds maximum")
        if field.get("type") == "month":
            default_value = field.get("default_value")
            if default_value not in (None, "") and not re.fullmatch(
                r"\d{4}-(?:0[1-9]|1[0-2])", str(default_value)
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Month field default must use YYYY-MM",
                )
        names.append(name)
    if len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Input field names must be unique")
    if "schedule" in triggers:
        schedule = config.get("schedule", {})
        expression = schedule.get("cron", "")
        if not croniter.is_valid(expression):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid schedule cron expression")
        try:
            ZoneInfo(schedule.get("timezone", "UTC"))
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid schedule timezone") from exc
        try:
            schedule_inputs = json.loads(schedule.get("inputs_json", "{}"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid schedule inputs JSON") from exc
        if not isinstance(schedule_inputs, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Schedule inputs must be an object")


def validate_template_config(config: dict[str, Any]) -> None:
    template = config.get("template")
    if not isinstance(template, str) or not template.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Template content is required")
    inputs = config.get("inputs", [])
    if not isinstance(inputs, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Template inputs must be an array")
    names: list[str] = []
    for item in inputs:
        if not isinstance(item, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid template input")
        name = str(item.get("name", ""))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid template input name")
        if not isinstance(item.get("value"), str) or not item["value"].strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Template input value is required")
        names.append(name)
    if len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Template input names must be unique")
    try:
        SandboxedEnvironment(undefined=StrictUndefined, autoescape=False).parse(template)
    except TemplateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid Jinja2 template") from exc


def validate_aggregate_config(config: dict[str, Any]) -> None:
    if config.get("group_enabled", False):
        groups = config.get("groups", [])
        if not isinstance(groups, list) or not groups:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aggregation groups are required")
        names: list[str] = []
        for group in groups:
            if not isinstance(group, dict):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid aggregation group")
            name = str(group.get("name", ""))
            variables = group.get("variables", [])
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid aggregation group name")
            if not isinstance(variables, list) or not any(isinstance(value, str) and value.strip() for value in variables):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aggregation group variables are required")
            names.append(name)
        if len(names) != len(set(names)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aggregation group names must be unique")
        return
    variables = config.get("variables", [])
    if not isinstance(variables, list) or not any(isinstance(value, str) and value.strip() for value in variables):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Aggregation variables are required")


def validate_variable_config(config: dict[str, Any]) -> None:
    assignments = config.get("assignments")
    if assignments is None and isinstance(config.get("values"), dict) and config["values"]:
        return
    if not isinstance(assignments, list) or not assignments:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Variable assignments are required")
    names: list[str] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid variable assignment")
        name = str(assignment.get("name", ""))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid variable assignment name")
        if assignment.get("type", "Any") not in {"String", "Number", "Boolean", "Object", "Array", "Any"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid variable assignment type")
        operation = assignment.get("operation", "overwrite")
        if operation not in {"overwrite", "append", "extend", "clear"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid variable assignment operation")
        if operation != "clear" and "value" not in assignment:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Variable assignment value is required")
        names.append(name)
    if len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Variable assignment names must be unique")


def validate_extract_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("source"), str) or not config["source"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Extraction input is required")
    if not isinstance(config.get("model"), str) or not config["model"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Extraction model is required")
    fields = config.get("fields")
    if not isinstance(fields, list) or not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Extraction fields are required")
    names: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid extraction field")
        name = str(field.get("name", ""))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid extraction field name")
        if field.get("type", "String") not in {"String", "Number", "Boolean", "Object", "Array"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid extraction field type")
        names.append(name)
    if len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Extraction field names must be unique")
    vision = config.get("vision", {"enabled": False})
    if not isinstance(vision, dict) or not isinstance(vision.get("enabled", False), bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid extraction vision config")
    if vision.get("enabled") and not str(vision.get("variable", "")).strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Extraction vision variable is required")


def validate_list_config(config: dict[str, Any]) -> None:
    if "source" not in config or config.get("source") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "List source is required")
    filter_config = config.get("filter", {})
    allowed_operators = {"equals", "not_equals", "contains", "not_contains", "greater_than", "less_than", "is_empty", "is_not_empty"}
    if filter_config.get("enabled") and filter_config.get("operator", "equals") not in allowed_operators:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid list filter operator")
    nth = config.get("nth", {})
    if nth.get("enabled") and (not isinstance(nth.get("index"), int) or nth["index"] < 1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid list item position")
    limit = config.get("limit", {})
    if limit.get("enabled") and (not isinstance(limit.get("count"), int) or limit["count"] < 0):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid list limit")
    sort_config = config.get("sort", {})
    if sort_config.get("enabled") and sort_config.get("order", "asc") not in {"asc", "desc"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid list sort order")


def validate_iteration_config(config: dict[str, Any]) -> None:
    if config.get("source") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Iteration source is required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", str(config.get("item_variable", "item"))):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid iteration item variable")
    if config.get("mode", "sequential") not in {"sequential", "parallel"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid iteration mode")
    concurrency = config.get("concurrency", 1)
    if not isinstance(concurrency, int) or not 1 <= concurrency <= 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid iteration concurrency")


def validate_loop_config(config: dict[str, Any]) -> None:
    if config.get("condition") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Loop condition is required")
    maximum = config.get("max_iterations", 10)
    if not isinstance(maximum, int) or not 1 <= maximum <= 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid loop iteration limit")


def validate_delay_config(config: dict[str, Any]) -> None:
    seconds = config.get("seconds", 1)
    if not isinstance(seconds, (int, float)) or not 0 <= seconds <= 86_400:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid delay duration")


def validate_wait_config(config: dict[str, Any]) -> None:
    if config.get("mode", "all") not in {"all", "any"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid wait mode")


def normalized_human_actions(config: dict[str, Any]) -> list[dict[str, Any]]:
    actions = config.get("actions")
    if isinstance(actions, list) and actions:
        return actions
    return [
        {"id": "approve", "label": "Approve", "value": "approved", "style": "primary"},
        {"id": "reject", "label": "Reject", "value": "rejected", "style": "danger"},
    ]


def validate_human_config(config: dict[str, Any]) -> None:
    if not str(config.get("form_content") or config.get("instructions") or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Human form content is required")
    methods = config.get("submission_methods", ["studio"])
    if not isinstance(methods, list) or not methods or not set(methods) <= {"studio", "link", "email"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid human submission methods")
    actions = normalized_human_actions(config)
    action_ids = [str(action.get("id", "")) for action in actions]
    if (
        any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", action_id) for action_id in action_ids)
        or len(action_ids) != len(set(action_ids))
        or any(not str(action.get("label", "")).strip() for action in actions)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid human actions")
    timeout_minutes = config.get("timeout_minutes", 4320)
    if not isinstance(timeout_minutes, int) or not 1 <= timeout_minutes <= 525600:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid human timeout")


def validate_end_config(config: dict[str, Any]) -> None:
    outputs = config.get("outputs")
    if isinstance(outputs, list):
        if not outputs:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "End node requires an output")
        names: list[str] = []
        allowed_types = {"String", "Number", "Boolean", "Object", "Array", "File", "Any"}
        for output in outputs:
            if not isinstance(output, dict):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid end output")
            name = str(output.get("name", ""))
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid end output name")
            if output.get("type", "Any") not in allowed_types:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid end output type")
            if "value" not in output or output.get("value") in (None, ""):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "End output value is required")
            names.append(name)
        if len(names) != len(set(names)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "End output names must be unique")
        return
    if isinstance(outputs, dict) and outputs:
        return
    if isinstance(outputs, str) and outputs.strip():
        return
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "End node requires an output")


def validate_condition_config(config: dict[str, Any]) -> None:
    conditions = config.get("conditions")
    if isinstance(conditions, list) and conditions:
        allowed_operators = {
            "equals", "not_equals", "contains", "not_contains", "starts_with", "ends_with",
            "greater_than", "less_than", "greater_or_equal", "less_or_equal", "is_empty",
            "is_not_empty", "in",
        }
        if config.get("logical_operator", "and") not in {"and", "or"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid condition logical operator")
        for clause in conditions:
            if not isinstance(clause, dict) or clause.get("operator") not in allowed_operators:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid condition clause")
            if clause.get("variable") in (None, ""):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Condition variable is required")
            if clause.get("operator") not in {"is_empty", "is_not_empty"} and clause.get("value") is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Condition value is required")
        return
    if isinstance(config.get("expression"), str) and config["expression"].strip():
        return
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Condition requires at least one clause")


def validate_classifier_config(config: dict[str, Any]) -> None:
    if config.get("input") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Classifier input is required")
    categories = config.get("categories")
    if not isinstance(categories, list) or len(categories) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Classifier requires at least two categories")
    ids: list[str] = []
    names: list[str] = []
    for category in categories:
        if not isinstance(category, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid classifier category")
        category_id = str(category.get("id", ""))
        name = str(category.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", category_id) or not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid classifier category")
        keywords = category.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(keyword, str) or not keyword.strip() for keyword in keywords):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid classifier category keywords")
        if not isinstance(category.get("description", ""), str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid classifier category description")
        ids.append(category_id)
        names.append(name.casefold())
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Classifier categories must be unique")


def validate_code_config(config: dict[str, Any]) -> None:
    inputs = config.get("inputs", [])
    outputs = config.get("outputs", [])
    if not isinstance(inputs, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Code inputs must be an array")
    if not isinstance(outputs, list) or not outputs:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Code outputs are required")
    allowed_input_types = {"String", "Number", "Boolean", "Object", "Array", "Any"}
    allowed_output_types = allowed_input_types | {"File"}
    input_names: list[str] = []
    output_names: list[str] = []
    for item in inputs:
        name = str(item.get("name", "")) if isinstance(item, dict) else ""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) or item.get("type", "Any") not in allowed_input_types or "value" not in item:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid code input")
        input_names.append(name)
    for item in outputs:
        name = str(item.get("name", "")) if isinstance(item, dict) else ""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) or item.get("type", "Any") not in allowed_output_types:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid code output")
        output_names.append(name)
    if len(input_names) != len(set(input_names)) or len(output_names) != len(set(output_names)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Code input and output names must be unique")
    timeout_seconds = config.get("timeout_seconds", 30)
    memory_mb = config.get("memory_mb", 256)
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid code timeout")
    if not isinstance(memory_mb, int) or not 64 <= memory_mb <= 2048:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid code memory limit")
    if not isinstance(config.get("network_enabled", False), bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid code network setting")
    validate_script(
        str(config.get("source", "")),
        str(config.get("entrypoint", "main")),
        {"type": "object"},
        {"type": "object"},
    )


def validate_llm_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("model"), str) or not config["model"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LLM model is required")
    messages = config.get("messages")
    if isinstance(messages, list) and messages:
        if any(
            not isinstance(message, dict)
            or message.get("role") not in {"system", "user", "assistant"}
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
            for message in messages
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM prompt message")
    elif not isinstance(config.get("prompt"), str) or not config["prompt"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LLM prompt messages are required")
    temperature = config.get("temperature", 0.7)
    top_p = config.get("top_p", 1)
    max_tokens = config.get("max_tokens", 1024)
    if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM temperature")
    if not isinstance(top_p, (int, float)) or not 0 <= top_p <= 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM top_p")
    if not isinstance(max_tokens, int) or not 1 <= max_tokens <= 128_000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM max tokens")
    response_format = config.get("response_format", "text")
    if response_format not in {"text", "json_object", "json_schema"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM response format")
    if response_format == "json_schema" and not isinstance(config.get("response_schema"), dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LLM response schema is required")
    context = config.get("context", "")
    if not isinstance(context, str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LLM context must be text")
    vision = config.get("vision", {"enabled": False})
    if not isinstance(vision, dict) or not isinstance(vision.get("enabled", False), bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM vision config")
    if vision.get("detail", "high") not in {"auto", "high", "low"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM vision detail")
    if vision.get("enabled") and (not isinstance(vision.get("variable"), str) or not vision["variable"].strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LLM vision variable is required")
    reasoning = config.get("reasoning", {"separate": False})
    if not isinstance(reasoning, dict) or not isinstance(reasoning.get("separate", False), bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid LLM reasoning config")


def validate_image_config(config: dict[str, Any]) -> None:
    for field in ("provider_id", "model", "prompt"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Image {field} is required")
    for field in ("count", "output_compression"):
        value = config.get(field, 1 if field == "count" else 80)
        if isinstance(value, str) and VARIABLE.search(value):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid image {field}") from exc
        minimum, maximum = (1, 10) if field == "count" else (0, 100)
        if not minimum <= number <= maximum:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid image {field}")
    if config.get("quality", "high") not in {"low", "medium", "high", "auto"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image quality")
    if config.get("output_format", "webp") not in {"png", "jpeg", "jpg", "webp"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image output format")
    if config.get("background", "auto") not in {"auto", "opaque", "transparent"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image background")
    timeout_seconds = config.get("timeout_seconds", 600)
    if not isinstance(timeout_seconds, (int, float)) or not 30 <= timeout_seconds <= 900:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid image timeout")


def validate_http_config(config: dict[str, Any]) -> None:
    method = str(config.get("method", "GET")).upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid HTTP method")
    url = str(config.get("url", "")).strip()
    is_variable_url = bool(re.fullmatch(r"\{\{[^{}]+\}\}", url))
    if not is_variable_url and not re.fullmatch(r"https?://[^\s]+", url, re.IGNORECASE):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "HTTP URL must use http or https")
    timeout_seconds = config.get("timeout_seconds", 30)
    if not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 300:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid HTTP timeout")
    for field in ("headers", "query"):
        value = config.get(field, {})
        if not isinstance(value, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"HTTP {field} must be an object")
    body_type = config.get("body_type", "json")
    if body_type not in {"none", "json", "raw", "form"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid HTTP body type")
    body = config.get("body")
    if body_type == "raw" and body is not None and not isinstance(body, str):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Raw HTTP body must be text")
    if body_type == "form" and body is not None and not isinstance(body, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Form HTTP body must be an object")
    auth = config.get("auth", {"type": "none"})
    if not isinstance(auth, dict) or auth.get("type", "none") not in {"none", "bearer", "basic", "api_key"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid HTTP authentication")
    if auth.get("type") == "bearer" and auth.get("token") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Bearer token is required")
    if auth.get("type") == "basic" and auth.get("username") in (None, ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Basic auth username is required")
    if auth.get("type") == "api_key":
        if auth.get("key") in (None, "") or auth.get("value") in (None, ""):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "API key name and value are required")
        if auth.get("location", "header") not in {"header", "query"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid API key location")
    max_response_bytes = config.get("max_response_bytes", 2_000_000)
    if not isinstance(max_response_bytes, int) or not 1024 <= max_response_bytes <= 10_000_000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid HTTP response size limit")


def validate_document_config(config: dict[str, Any]) -> None:
    operation = config.get("operation", "extract")
    if operation not in {"extract", "fill_answers"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid document operation")
    if not isinstance(config.get("source"), str) or not config["source"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Document source file is required")
    if operation == "extract":
        if config.get("extract_mode", "text") not in {"text", "text_tables", "text_images"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid document extraction mode")
        if not isinstance(config.get("ocr_fallback", True), bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid document OCR fallback")
    elif not isinstance(config.get("answers"), str) or not config["answers"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Document answer plan is required")


def validate_answer_filler_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get("source"), str) or not config["source"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Answer filler source file is required")
    if not isinstance(config.get("answers"), str) or not config["answers"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Answer filler plan is required")


def validate_execution_policy(config: dict[str, Any]) -> None:
    retry = config.get("retry", {"enabled": False})
    if not isinstance(retry, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid node retry policy")
    if retry.get("enabled", False):
        max_retries = retry.get("max_retries", 3)
        interval_seconds = retry.get("interval_seconds", 0)
        if not isinstance(max_retries, int) or not 1 <= max_retries <= 10:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Node retries must be between 1 and 10")
        if not isinstance(interval_seconds, (int, float)) or not 0 <= interval_seconds <= 30:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Node retry interval must be between 0 and 30 seconds")
    strategy = config.get("error_strategy", "fail")
    if strategy not in {"fail", "default_value", "error_branch"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid node error strategy")
    if strategy == "default_value" and not isinstance(config.get("default_output", {}), dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Default node output must be an object")


def validate_run_inputs(graph: dict[str, Any], inputs: dict[str, Any]) -> None:
    start = next(node for node in graph.get("nodes", []) if node.get("type") == "start")
    fields = start.get("data", {}).get("config", {}).get("input_fields", [])
    for field in fields:
        name = field["name"]
        value = inputs.get(name)
        if field.get("required") and (value is None or value == "" or value == []):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' is required")
        if value is None:
            continue
        field_type = field.get("type", "text")
        if field_type == "number" and not isinstance(value, (int, float)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' must be a number")
        if field_type in {"text", "textarea", "select"} and not isinstance(value, str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' must be text")
        if field_type == "select" and value not in field.get("options", []):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' is not an allowed option")
        if field.get("max_length") and isinstance(value, str) and len(value) > field["max_length"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' is too long")
        if field_type == "number":
            if field.get("min") is not None and value < field["min"]:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' is below the minimum")
            if field.get("max") is not None and value > field["max"]:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' is above the maximum")
        if field_type == "file" and not isinstance(value, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' must be a file")
        if field_type == "files" and not isinstance(value, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Input '{name}' must be a file list")


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if not isinstance(value, str):
        return value
    full_match = VARIABLE.fullmatch(value)
    if full_match:
        return lookup(context, full_match.group(1))
    return VARIABLE.sub(lambda match: str(lookup(context, match.group(1)) or ""), value)


def lookup(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in (segment.strip() for segment in path.split(".")):
        if not isinstance(current, dict):
            return None
        if (
            part == "stem"
            and part not in current
            and isinstance(current.get("filename"), str)
        ):
            filename = str(current["filename"]).replace("\\", "/")
            current = PurePosixPath(filename).stem
        else:
            current = current.get(part)
    return current


TRACE_INPUT_KEYS: dict[str, tuple[str, ...]] = {
    "end": ("outputs",),
    "llm": ("provider_id", "model", "messages", "prompt", "context", "vision", "response_format"),
    "image": ("provider_id", "model", "prompt", "size", "count", "quality", "output_format", "timeout_seconds"),
    "agent": ("provider_id", "model", "query", "instructions", "tools", "memory"),
    "classifier": ("input", "categories"),
    "code": ("inputs",),
    "script": ("script_id", "version", "inputs"),
    "template": ("inputs", "template"),
    "variable": ("assignments",),
    "json": ("value",),
    "aggregate": ("variables", "groups"),
    "extract": ("source", "fields", "instruction"),
    "list": ("source", "filter", "nth", "limit", "sort", "unique"),
    "http": ("method", "url", "query", "headers", "body_type", "body"),
    "condition": ("logical_operator", "conditions", "expression"),
    "human": ("form_content", "submission_methods", "actions"),
    "iteration": ("source", "item_variable", "mode", "concurrency"),
    "loop": ("condition", "max_iterations"),
    "wait": ("mode",),
    "delay": ("seconds",),
    "subworkflow": ("workflow_id", "inputs"),
    "document": ("operation", "source", "answers", "extract_mode", "output_name"),
    "answer_filler": ("source", "answers", "output_name"),
}


def redact_trace_value(value: Any, secrets: list[Any]) -> Any:
    if isinstance(value, dict):
        return {key: redact_trace_value(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_trace_value(item, secrets) for item in value]
    for secret in secrets:
        if secret in (None, ""):
            continue
        if value == secret:
            return "••••••••"
        if isinstance(value, str) and isinstance(secret, str) and secret in value:
            value = value.replace(secret, "••••••••")
    return value


def build_node_trace_input(node: dict[str, Any], context: dict[str, Any]) -> Any:
    node_type = str(node.get("type") or "")
    if node_type == "start":
        value: Any = deepcopy(context.get("inputs", {}))
    else:
        config = node.get("data", {}).get("config", {})
        resolved = resolve_value(deepcopy(config), context)
        keys = TRACE_INPUT_KEYS.get(node_type)
        value = {key: resolved.get(key) for key in keys if key in resolved} if keys else resolved
    environment = context.get("env", {})
    secrets = list(environment.values()) if isinstance(environment, dict) else []
    return redact_trace_value(value, secrets)


def trace_json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8"))


def normalize_trace_usage(output: Any) -> dict[str, int]:
    usage = output.get("_usage") or output.get("usage") if isinstance(output, dict) else None
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    return {"input_tokens": max(0, input_tokens), "output_tokens": max(0, output_tokens), "total_tokens": max(0, total_tokens)}


def build_node_trace_metadata(
    node: dict[str, Any], trace_input: Any, output: Any, duration_ms: float, attempts: int,
    context: dict[str, Any],
) -> dict[str, Any]:
    node_type = str(node.get("type") or "")
    executor = "sandbox" if node_type in {"code", "script"} else "network" if node_type == "http" else "model" if node_type in {"llm", "image", "agent", "classifier", "extract"} else "built-in"
    environment = context.get("env", {})
    secrets = list(environment.values()) if isinstance(environment, dict) else []
    logs = output.get("_logs", []) if isinstance(output, dict) else []
    return {
        "executor": executor,
        "duration_ms": max(0, round(duration_ms, 2)),
        "attempts": max(0, int(attempts)),
        "retry_count": max(0, int(attempts) - 1),
        "input_bytes": trace_json_size(trace_input),
        "output_bytes": trace_json_size(output),
        "usage": normalize_trace_usage(output),
        "logs": redact_trace_value(logs if isinstance(logs, list) else [str(logs)], secrets),
    }


def execute_parallel_graph(
    graph: dict[str, Any], inputs: dict[str, Any], environment: dict[str, Any] | None = None,
    system: dict[str, Any] | None = None,
    model_providers: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node.get("type") != "note" and not node.get("parentNode")
    }
    incoming = defaultdict(int)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if edge["source"] in nodes and edge["target"] in nodes:
            incoming[edge["target"]] += 1
            outgoing[edge["source"]].append(edge)
    ready = deque(node_id for node_id in nodes if incoming[node_id] == 0)
    reachable = {node_id for node_id, node in nodes.items() if node.get("type") == "start"}
    context: dict[str, Any] = {
        "inputs": deepcopy(inputs),
        "env": deepcopy(environment or {}),
        "sys": deepcopy(system or {}),
        "__model_providers__": model_providers or {},
    }
    trace: list[dict[str, Any]] = []
    running: dict[Future[Any], str] = {}
    visited = 0

    def run_node(node_id: str, run_context: dict[str, Any]) -> dict[str, Any]:
        node = nodes[node_id]
        started = datetime.now(UTC)
        trace_input = build_node_trace_input(node, run_context)
        output, execution_status, execution_error, execution_attempts = execute_node_with_policy(node, run_context, graph)
        return {
            "output": output,
            "status": execution_status,
            "error": execution_error,
            "attempts": execution_attempts,
            "trace_input": trace_input,
            "started": started,
            "finished": datetime.now(UTC),
            "context": run_context,
        }

    def complete_node(node_id: str, execution: dict[str, Any] | None) -> None:
        nonlocal visited
        node = nodes[node_id]
        node_type = node.get("type")
        output = execution["output"] if execution else None
        execution_status = execution["status"] if execution else "skipped"
        if execution:
            store_node_output(context, node, output, graph)
            duration_ms = (execution["finished"] - execution["started"]).total_seconds() * 1000
            trace.append({
                "node_id": node_id,
                "node_type": node_type,
                "status": execution_status,
                "input": execution["trace_input"],
                "output": output,
                "metadata": build_node_trace_metadata(
                    node, execution["trace_input"], output, duration_ms, execution["attempts"], execution["context"]
                ),
                "error": execution["error"],
                "attempts": execution["attempts"],
                "error_handled": execution_status == "recovered",
                "started_at": execution["started"].isoformat(),
                "finished_at": execution["finished"].isoformat(),
            })
        visited += 1
        active_branch = None
        if execution and node_type == "condition":
            active_branch = "true" if bool(output.get("result")) else "false"
        elif execution and node_type == "classifier":
            active_branch = str(output.get("branch") or "")
        elif execution and execution_status == "recovered" and node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch":
            active_branch = "error"
        for edge in outgoing[node_id]:
            target = edge["target"]
            edge_handle = str(edge.get("sourceHandle") or "")
            uses_error_branch = node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch"
            branch_matches = edge_handle == active_branch if active_branch is not None else not (uses_error_branch and edge_handle == "error")
            active_edge = node_id in reachable and branch_matches
            if active_edge:
                reachable.add(target)
            wait_mode = nodes[target].get("data", {}).get("config", {}).get("mode", "all") if nodes[target].get("type") == "wait" else "all"
            if wait_mode == "any":
                if active_edge and incoming[target] > 0:
                    incoming[target] = 0
                    ready.append(target)
                continue
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(nodes)))) as executor:
        while ready or running:
            while ready:
                node_id = ready.popleft()
                if node_id not in reachable:
                    complete_node(node_id, None)
                    continue
                running[executor.submit(run_node, node_id, deepcopy(context))] = node_id
            if not running:
                continue
            completed, _ = wait_for_futures(running, return_when=FIRST_COMPLETED)
            for future in completed:
                node_id = running.pop(future)
                complete_node(node_id, future.result())
    if visited != len(nodes):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph contains an unsupported cycle")
    end_nodes = [node for node in nodes.values() if node.get("type") == "end"]
    executed_end = next((node for node in reversed(end_nodes) if node["id"] in context), None)
    return context.get(executed_end["id"], {}) if executed_end else {}, trace


def checkpoint_context(context: dict[str, Any]) -> dict[str, Any]:
    checkpoint = deepcopy(context)
    checkpoint.pop("__model_providers__", None)
    checkpoint.pop("__event_callback__", None)
    checkpoint.pop("__cancellation_callback__", None)
    return checkpoint


def ensure_workflow_not_cancelled(context: dict[str, Any]) -> None:
    callback = context.get("__cancellation_callback__")
    if callable(callback) and callback():
        raise WorkflowCancelled("Workflow run was cancelled")


def execute_graph(
    graph: dict[str, Any], inputs: dict[str, Any], resume_state: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    system: dict[str, Any] | None = None,
    model_providers: dict[str, dict[str, Any]] | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    cancellation_callback: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Execute a validated workflow graph with runtime-only provider credentials."""
    validate_graph(graph)
    validate_run_inputs(graph, inputs)
    pause_capable = any(
        node.get("type") in {"human", "subworkflow"} and not node.get("parentNode")
        for node in graph.get("nodes", [])
    )
    if (
        not resume_state
        and not pause_capable
        and event_callback is None
        and cancellation_callback is None
    ):
        return execute_parallel_graph(
            graph,
            inputs,
            environment=environment,
            system=system,
            model_providers=model_providers,
        )
    nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node.get("type") != "note" and not node.get("parentNode")
    }
    incoming = defaultdict(int)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if edge["source"] not in nodes or edge["target"] not in nodes:
            continue
        incoming[edge["target"]] += 1
        outgoing[edge["source"]].append(edge)
    if resume_state:
        incoming = defaultdict(int, {str(key): int(value) for key, value in resume_state.get("incoming", {}).items()})
        queue = deque(str(node_id) for node_id in resume_state.get("queue", []))
        context = deepcopy(resume_state.get("context", {"inputs": deepcopy(inputs), "env": deepcopy(environment or {}), "sys": deepcopy(system or {})}))
        reachable = set(str(node_id) for node_id in resume_state.get("reachable", []))
        trace = deepcopy(resume_state.get("trace", []))
        visited = int(resume_state.get("visited", 0))
        context["__model_providers__"] = model_providers or {}
        context["__event_callback__"] = event_callback
        context["__cancellation_callback__"] = cancellation_callback
    else:
        queue = deque(node_id for node_id in nodes if incoming[node_id] == 0)
        context: dict[str, Any] = {
            "inputs": deepcopy(inputs),
            "env": deepcopy(environment or {}),
            "sys": deepcopy(system or {}),
            "__model_providers__": model_providers or {},
            "__event_callback__": event_callback,
            "__cancellation_callback__": cancellation_callback,
        }
        reachable = {node_id for node_id, node in nodes.items() if node.get("type") == "start"}
        trace: list[dict[str, Any]] = []
        visited = 0
    while queue:
        ensure_workflow_not_cancelled(context)
        node_id = queue.popleft()
        node = nodes[node_id]
        node_type = node.get("type")
        started = datetime.now(UTC)
        output = None
        execution_status = "succeeded"
        execution_error: str | None = None
        execution_attempts = 0
        if node_id in reachable:
            if event_callback:
                event_callback({"type": "node_started", "node_id": node_id, "node_type": node_type})
            trace_input = build_node_trace_input(node, context)
            if node_type == "human" and node_id not in context.get("__human_responses__", {}):
                config = resolve_value(node.get("data", {}).get("config", {}), context)
                request = {
                    "title": node.get("data", {}).get("label") or "Human approval",
                    "form_content": config.get("form_content") or config.get("instructions") or "",
                    "submission_methods": config.get("submission_methods", ["studio"]),
                    "actions": normalized_human_actions(config),
                    "timeout_minutes": int(config.get("timeout_minutes", 4320)),
                }
                raise WorkflowPause(
                    node_id,
                    request,
                    {
                        "queue": [node_id, *queue],
                        "incoming": dict(incoming),
                        "context": checkpoint_context(context),
                        "reachable": list(reachable),
                        "trace": trace,
                        "visited": visited,
                    },
                )
            try:
                output, execution_status, execution_error, execution_attempts = execute_node_with_policy(node, context, graph)
            except WorkflowPause as pause:
                if node_type != "subworkflow":
                    raise
                context.setdefault("__subworkflow_resume__", {})[node_id] = pause.resume_state
                request = {
                    **pause.request,
                    "_response_node_id": pause.request.get("_response_node_id", pause.node_id),
                    "subworkflow_path": f"{node_id}/{pause.node_id}",
                }
                raise WorkflowPause(
                    f"{node_id}/{pause.node_id}",
                    request,
                    {
                        "queue": [node_id, *queue],
                        "incoming": dict(incoming),
                        "context": checkpoint_context(context),
                        "reachable": list(reachable),
                        "trace": trace,
                        "visited": visited,
                    },
                ) from pause
            store_node_output(context, node, output, graph)
            ensure_workflow_not_cancelled(context)
            finished = datetime.now(UTC)
            duration_ms = (finished - started).total_seconds() * 1000
            trace.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "status": execution_status,
                    "input": trace_input,
                    "output": output,
                    "metadata": build_node_trace_metadata(node, trace_input, output, duration_ms, execution_attempts, context),
                    "error": execution_error,
                    "attempts": execution_attempts,
                    "error_handled": execution_status == "recovered",
                    "started_at": started.isoformat(),
                    "finished_at": finished.isoformat(),
                }
            )
            if event_callback:
                event_callback(
                    {
                        "type": "node_finished",
                        "node_id": node_id,
                        "node_type": node_type,
                        "status": execution_status,
                        "duration_ms": duration_ms,
                    }
                )
        visited += 1
        active_branch = None
        if node_id in reachable and node_type == "condition":
            active_branch = "true" if bool(output.get("result")) else "false"
        elif node_id in reachable and node_type == "classifier":
            active_branch = str(output.get("branch") or "")
        elif node_id in reachable and node_type == "human":
            active_branch = f"action:{output.get('action_id')}"
        elif node_id in reachable and execution_status == "recovered" and node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch":
            active_branch = "error"
        for edge in outgoing[node_id]:
            target = edge["target"]
            edge_handle = str(edge.get("sourceHandle") or "")
            uses_error_branch = node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch"
            human_uses_action_branches = node_type == "human" and any(
                str(item.get("sourceHandle") or "").startswith("action:") for item in outgoing[node_id]
            )
            branch_matches = (
                edge_handle == active_branch or (node_type == "human" and not human_uses_action_branches and edge_handle == "")
                if active_branch is not None
                else not (uses_error_branch and edge_handle == "error")
            )
            if node_id in reachable and branch_matches:
                reachable.add(target)
            if nodes[target].get("type") == "wait" and nodes[target].get("data", {}).get("config", {}).get("mode", "all") == "any":
                if node_id in reachable and branch_matches and incoming[target] > 0:
                    incoming[target] = 0
                    queue.append(target)
                continue
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if visited != len(nodes):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Graph contains an unsupported cycle"
        )
    end_nodes = [node for node in nodes.values() if node.get("type") == "end"]
    executed_end = next((node for node in reversed(end_nodes) if node["id"] in context), None)
    return context.get(executed_end["id"], {}) if executed_end else {}, trace


def execute_container_body(
    graph: dict[str, Any], container: dict[str, Any], context: dict[str, Any]
) -> tuple[Any, dict[str, Any]]:
    container_id = str(container["id"])
    children = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if node.get("parentNode") == container_id
    }
    if not children:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Container body is empty")
    incoming = defaultdict(int)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        if edge.get("source") in children and edge.get("target") in children:
            incoming[edge["target"]] += 1
            outgoing[edge["source"]].append(edge)
    queue = deque(node_id for node_id in children if incoming[node_id] == 0)
    reachable = set(queue)
    visited = 0
    last_output: Any = None
    while queue:
        ensure_workflow_not_cancelled(context)
        node_id = queue.popleft()
        node = children[node_id]
        output = None
        execution_status = "succeeded"
        if node_id in reachable:
            output, execution_status, _, _ = execute_node_with_policy(node, context, graph)
            store_node_output(context, node, output, graph)
            last_output = output
        visited += 1
        active_branch = None
        if node_id in reachable and node.get("type") == "condition":
            active_branch = "true" if bool((output or {}).get("result")) else "false"
        elif node_id in reachable and node.get("type") == "classifier":
            active_branch = str((output or {}).get("branch") or "")
        elif node_id in reachable and execution_status == "recovered" and node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch":
            active_branch = "error"
        for edge in outgoing[node_id]:
            target = edge["target"]
            edge_handle = str(edge.get("sourceHandle") or "")
            uses_error_branch = node.get("data", {}).get("config", {}).get("error_strategy") == "error_branch"
            branch_matches = edge_handle == active_branch if active_branch is not None else not (uses_error_branch and edge_handle == "error")
            if node_id in reachable and branch_matches:
                reachable.add(target)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if visited != len(children):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Container body contains an unsupported cycle")
    output_selector = container.get("data", {}).get("config", {}).get("output")
    return (resolve_value(output_selector, context) if output_selector not in (None, "") else last_output), context


def execute_container_node(
    graph: dict[str, Any], node: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    raw_config = node.get("data", {}).get("config", {})
    if node.get("type") == "iteration":
        source = resolve_value(raw_config.get("source"), context)
        if not isinstance(source, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Iteration source must resolve to an array")
        item_variable = str(raw_config.get("item_variable", "item"))
        def run_item(index_item: tuple[int, Any]) -> Any:
            ensure_workflow_not_cancelled(context)
            index, item = index_item
            nested_context = deepcopy(context)
            nested_context[item_variable] = item
            store_node_output(nested_context, node, {item_variable: item, "item": item, "index": index}, graph)
            output, _ = execute_container_body(graph, node, nested_context)
            return output

        indexed_items = list(enumerate(source))
        if raw_config.get("mode", "sequential") == "parallel" and len(indexed_items) > 1:
            with ThreadPoolExecutor(max_workers=min(int(raw_config.get("concurrency", 1)), len(indexed_items))) as executor:
                results = list(executor.map(run_item, indexed_items))
        else:
            results = [run_item(index_item) for index_item in indexed_items]
        return {"results": results, "count": len(results)}
    maximum = int(raw_config.get("max_iterations", 10))
    last_output: Any = None
    completed = False
    iterations = 0
    loop_context = deepcopy(context)
    for index in range(maximum):
        ensure_workflow_not_cancelled(loop_context)
        store_node_output(loop_context, node, {"index": index, "iteration": index + 1, "previous": last_output}, graph)
        last_output, loop_context = execute_container_body(graph, node, loop_context)
        iterations = index + 1
        if bool(resolve_value(raw_config.get("condition"), loop_context)):
            completed = True
            break
    return {"result": last_output, "iterations": iterations, "completed": completed}


def execute_node_with_policy(
    node: dict[str, Any], context: dict[str, Any], graph: dict[str, Any] | None = None
) -> tuple[Any, str, str | None, int]:
    config = node.get("data", {}).get("config", {})
    if node.get("type") not in EXECUTION_POLICY_NODE_TYPES:
        return execute_node(node, context), "succeeded", None, 1
    validate_execution_policy(config)
    retry = config.get("retry", {})
    max_attempts = 1 + (int(retry.get("max_retries", 3)) if retry.get("enabled", False) else 0)
    interval_seconds = float(retry.get("interval_seconds", 0))
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        ensure_workflow_not_cancelled(context)
        try:
            output = execute_container_node(graph, node, context) if graph and node.get("type") in {"iteration", "loop"} else execute_node(node, context)
            return output, "succeeded", None, attempt
        except (WorkflowPause, WorkflowCancelled):
            raise
        except Exception as exc:  # noqa: BLE001 - node boundaries intentionally isolate executor failures
            last_error = exc
            if attempt < max_attempts and interval_seconds:
                remaining = interval_seconds
                while remaining > 0:
                    ensure_workflow_not_cancelled(context)
                    interval = min(remaining, 0.25)
                    sleep(interval)
                    remaining -= interval
    assert last_error is not None
    error_message = workflow_error_message(last_error)
    strategy = config.get("error_strategy", "fail")
    if strategy == "default_value":
        output = resolve_value(deepcopy(config.get("default_output", {})), context)
        return output, "recovered", error_message, max_attempts
    if strategy == "error_branch":
        output = {
            "branch": "error",
            "error_type": type(last_error).__name__,
            "error_message": error_message,
        }
        return output, "recovered", error_message, max_attempts
    raise last_error


def workflow_error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return str(error.detail)
    return str(error) or type(error).__name__


def render_jinja_template(config: dict[str, Any], context: dict[str, Any]) -> str:
    bindings = {
        item["name"]: resolve_value(item.get("value"), context)
        for item in config.get("inputs", [])
        if isinstance(item, dict) and item.get("name")
    }
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    try:
        return environment.from_string(config.get("template", "")).render(**context, **bindings)
    except TemplateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Template rendering failed: {exc}") from exc


def execute_node(node: dict[str, Any], context: dict[str, Any]) -> Any:
    """Execute one node against an explicit context for graph and preview runs."""
    node_type = node.get("type")
    raw_config = node.get("data", {}).get("config", {})
    config = resolve_value(raw_config, context)
    event_callback = context.get("__event_callback__")
    if callable(event_callback) and node_type in {"llm", "agent", "extract"}:
        config["_stream_callback"] = lambda delta: event_callback(
            {"type": "token", "node_id": str(node.get("id")), "delta": delta}
        )
    registered, registered_output = execute_registered_node(str(node_type), config, context)
    if registered:
        return registered_output
    if node_type == "template":
        return {"text": render_jinja_template(raw_config, context)}
    if node_type == "code":
        return execute_code_node(config)
    if node_type == "script":
        runtime = raw_config.get("_script_runtime")
        if not isinstance(runtime, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Script runtime was not resolved",
            )
        script_inputs = config.get("inputs", {})
        if isinstance(script_inputs, list):
            script_inputs = {
                str(item.get("name")): item.get("value")
                for item in script_inputs
                if isinstance(item, dict) and item.get("name")
            }
        if not isinstance(script_inputs, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Script inputs must be an object")
        return execute_script_runtime(runtime, script_inputs)
    if node_type == "llm":
        return execute_llm(require_model_runtime(config, context), config)
    if node_type == "image":
        return execute_image_generation(require_model_runtime(config, context), config)
    if node_type == "agent":
        raw_tools = {
            str(tool.get("id")): tool
            for tool in raw_config.get("tools", [])
            if isinstance(tool, dict)
        }
        for tool in config.get("tools", []):
            source = raw_tools.get(str(tool.get("id")), {})
            if isinstance(source.get("_script_runtime"), dict):
                tool["_script_runtime"] = source["_script_runtime"]
        return execute_agent(
            require_model_runtime(config, context),
            config,
            execute_agent_tool,
        )
    if node_type == "extract":
        if config.get("provider_id"):
            return execute_extractor(require_model_runtime(config, context), config)
        return extract_structured_parameters(config)
    if node_type == "http":
        return execute_http_request(config)
    if node_type == "delay":
        remaining = float(config.get("seconds", 1))
        while remaining > 0:
            ensure_workflow_not_cancelled(context)
            interval = min(remaining, 0.25)
            sleep(interval)
            remaining -= interval
        return {"seconds": float(config.get("seconds", 1))}
    if node_type == "document":
        return execute_document(config)
    if node_type == "answer_filler":
        return fill_docx_answers(
            config.get("source"),
            config.get("answers"),
            output_name=str(config.get("output_name") or ""),
        )
    if node_type == "subworkflow":
        child_graph = raw_config.get("_resolved_graph")
        if not isinstance(child_graph, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Sub-workflow reference has not been resolved",
            )
        child_inputs = resolve_value(raw_config.get("inputs", {}), context)
        if not isinstance(child_inputs, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Sub-workflow inputs must resolve to an object",
            )
        node_id = str(node.get("id"))
        child_resume = deepcopy(context.get("__subworkflow_resume__", {}).get(node_id))
        if child_resume:
            child_context = child_resume.setdefault("context", {})
            child_context.setdefault("__human_responses__", {}).update(
                deepcopy(context.get("__human_responses__", {}))
            )
        child_system = deepcopy(context.get("sys", {}))
        child_system["workflow_id"] = str(raw_config.get("workflow_id") or child_system.get("workflow_id", ""))
        outputs, child_trace = execute_graph(
            child_graph,
            child_inputs,
            resume_state=child_resume,
            system=child_system,
            model_providers=context.get("__model_providers__", {}),
            cancellation_callback=context.get("__cancellation_callback__"),
        )
        context.get("__subworkflow_resume__", {}).pop(node_id, None)
        return {**outputs, "outputs": outputs, "_trace": child_trace}
    if node_type == "human":
        response = context.get("__human_responses__", {}).get(str(node.get("id")))
        if not isinstance(response, dict):
            raise HTTPException(status.HTTP_409_CONFLICT, "Human response is not available")
        action_id = str(response.get("action_id", ""))
        action = next(
            (item for item in normalized_human_actions(raw_config) if str(item.get("id")) == action_id),
            None,
        )
        if not action:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown human action")
        return {
            "action_id": action_id,
            "action_value": action.get("value", action_id),
            "approved": action_id.casefold() in {"approve", "approved", "accept", "accepted"},
            "data": response.get("data", {}),
            "comment": response.get("comment", ""),
            "responded_by": response.get("responded_by"),
        }
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        f"Unsupported node type: {node_type or '<missing>'}",
    )


def require_model_runtime(
    config: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    provider_id = str(config.get("provider_id", "")).strip()
    if not provider_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Model provider is required")
    runtime = context.get("__model_providers__", {}).get(provider_id)
    if not runtime:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Model provider is missing or belongs to another workspace",
        )
    return runtime


def execute_sandbox(
    source: str,
    entrypoint: str,
    inputs: dict[str, Any],
    timeout_seconds: int = 30,
    memory_mb: int = 256,
    network_enabled: bool = False,
    source_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    try:
        with httpx.Client(timeout=timeout_seconds + 5) as client:
            response = client.post(
                f"{settings.sandbox_url}/execute",
                json={
                    "source": source,
                    "source_files": source_files or {},
                    "entrypoint": entrypoint,
                    "inputs": inputs,
                    "timeout_seconds": timeout_seconds,
                    "memory_mb": memory_mb,
                    "network_enabled": network_enabled,
                },
                headers={"X-Sandbox-Token": settings.sandbox_shared_secret},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Sandbox unavailable: {exc}") from exc
    if result.get("status") != "succeeded":
        error = str(result.get("error") or "Python execution failed")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error[-4000:])
    raw_outputs = result.get("outputs")
    if not isinstance(raw_outputs, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Python entrypoint must return an object")
    sandbox_outputs = consume_sandbox_artifacts(raw_outputs)
    sandbox_outputs["_logs"] = result.get("logs", [])
    sandbox_outputs["_elapsed_ms"] = result.get("elapsed_ms", 0)
    return sandbox_outputs


def execute_code_node(config: dict[str, Any]) -> dict[str, Any]:
    validate_code_config(config)
    code_inputs = {str(item["name"]): item.get("value") for item in config.get("inputs", [])}
    sandbox_outputs = execute_sandbox(
        config["source"],
        config.get("entrypoint", "main"),
        code_inputs,
        int(config.get("timeout_seconds", 30)),
        int(config.get("memory_mb", 256)),
        bool(config.get("network_enabled", False)),
    )
    output: dict[str, Any] = {}
    for declared in config.get("outputs", []):
        name = str(declared["name"])
        value = sandbox_outputs.get(name)
        output[name] = coerce_assignment_value(value, declared.get("type", "Any")) if value is not None else None
    output["_logs"] = sandbox_outputs.get("_logs", [])
    output["_elapsed_ms"] = sandbox_outputs.get("_elapsed_ms", 0)
    return output


def execute_script_runtime(runtime: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    input_schema = runtime.get("input_schema", {})
    if isinstance(input_schema, dict) and input_schema:
        validate_inputs(input_schema, inputs)
    outputs = execute_sandbox(
        str(runtime.get("source", "")),
        str(runtime.get("entrypoint", "main")),
        inputs,
        network_enabled=bool(runtime.get("network_enabled", False)),
        source_files=runtime.get("source_files") if isinstance(runtime.get("source_files"), dict) else None,
    )
    clean_outputs = {key: value for key, value in outputs.items() if not key.startswith("_")}
    output_schema = runtime.get("output_schema", {})
    if isinstance(output_schema, dict) and output_schema:
        validate_inputs(output_schema, sandbox_schema_value(clean_outputs))
    return outputs


def execute_agent_tool(tool: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    if tool.get("type") != "script" or not isinstance(tool.get("_script_runtime"), dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Agent tool is not executable")
    return execute_script_runtime(tool["_script_runtime"], arguments)


def execute_http_request(
    config: dict[str, Any], transport: httpx.BaseTransport | None = None
) -> dict[str, Any]:
    validate_http_config(config)
    method = str(config.get("method", "GET")).upper()
    headers = {str(key): str(value) for key, value in config.get("headers", {}).items()}
    query = {str(key): value for key, value in config.get("query", {}).items()}
    auth_config = config.get("auth", {"type": "none"})
    auth: httpx.Auth | None = None
    if auth_config.get("type") == "bearer":
        headers.setdefault("Authorization", f"Bearer {auth_config['token']}")
    elif auth_config.get("type") == "basic":
        auth = httpx.BasicAuth(str(auth_config.get("username", "")), str(auth_config.get("password", "")))
    elif auth_config.get("type") == "api_key":
        if auth_config.get("location", "header") == "query":
            query[str(auth_config["key"])] = auth_config["value"]
        else:
            headers.setdefault(str(auth_config["key"]), str(auth_config["value"]))

    request_kwargs: dict[str, Any] = {"params": query, "headers": headers, "auth": auth}
    body_type = config.get("body_type", "json")
    body = config.get("body")
    if body_type == "json" and body is not None:
        request_kwargs["json"] = body
    elif body_type == "form" and body is not None:
        request_kwargs["data"] = body
    elif body_type == "raw" and body is not None:
        request_kwargs["content"] = body

    started = datetime.now(UTC)
    try:
        with httpx.Client(
            timeout=float(config.get("timeout_seconds", 30)),
            follow_redirects=bool(config.get("follow_redirects", False)),
            transport=transport,
        ) as client:
            with client.stream(method, str(config["url"]), **request_kwargs) as response:
                max_response_bytes = int(config.get("max_response_bytes", 2_000_000))
                chunks: list[bytes] = []
                response_size = 0
                for chunk in response.iter_bytes():
                    response_size += len(chunk)
                    if response_size > max_response_bytes:
                        raise HTTPException(
                            status.HTTP_502_BAD_GATEWAY,
                            "HTTP response exceeded the configured size limit",
                        )
                    chunks.append(chunk)
                response_body_bytes = b"".join(chunks)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"HTTP request failed: {exc}") from exc
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            response_body: Any = json.loads(response_body_bytes)
        except (UnicodeDecodeError, ValueError):
            response_body = response_body_bytes.decode(response.encoding or "utf-8", errors="replace")
    else:
        response_body = response_body_bytes.decode(response.encoding or "utf-8", errors="replace")
    safe_url = response.url.copy_with()
    if auth_config.get("type") == "api_key" and auth_config.get("location", "header") == "query":
        safe_url = safe_url.copy_set_param(str(auth_config["key"]), "[REDACTED]")
    sensitive_response_headers = {"authorization", "proxy-authorization", "set-cookie", "x-api-key"}
    safe_headers = {
        key: "[REDACTED]" if key.lower() in sensitive_response_headers else value
        for key, value in response.headers.items()
    }
    return {
        "status_code": response.status_code,
        "headers": safe_headers,
        "body": response_body,
        "url": str(safe_url),
        "elapsed_ms": max(0, round((datetime.now(UTC) - started).total_seconds() * 1000, 2)),
        "ok": response.is_success,
    }


def execute_node_preview(
    node: dict[str, Any],
    inputs: dict[str, Any],
    environment: dict[str, Any] | None = None,
    system: dict[str, Any] | None = None,
    model_providers: dict[str, dict[str, Any]] | None = None,
) -> tuple[Any, dict[str, Any]]:
    started = datetime.now(UTC)
    output, execution_status, execution_error, execution_attempts = execute_node_with_policy(
        node,
        {
            "inputs": deepcopy(inputs),
            "env": deepcopy(environment or {}),
            "sys": deepcopy(system or {}),
            "__model_providers__": model_providers or {},
        },
    )
    trace = {
        "node_id": node.get("id"),
        "node_type": node.get("type"),
        "status": execution_status,
        "output": output,
        "error": execution_error,
        "attempts": execution_attempts,
        "error_handled": execution_status == "recovered",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    return output, trace


def resolve_script_references(
    graph: dict[str, Any], latest_versions: dict[str, tuple[str, int]]
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for node in graph.get("nodes", []):
        node_type = node.get("type")
        config = node.get("data", {}).get("config", {})
        if node_type == "agent":
            for tool in config.get("tools", []):
                if not tool.get("enabled", True) or tool.get("type") != "script":
                    continue
                script_id = tool.get("reference_id")
                if not script_id or script_id not in latest_versions:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        f"Agent tool {tool.get('name') or tool.get('id')} is invalid",
                    )
                version_id, version = latest_versions[script_id]
                resolved[f"{node['id']}:{tool.get('id') or script_id}"] = {
                    "kind": "agent_tool",
                    "tool_id": tool.get("id"),
                    "script_id": script_id,
                    "script_version_id": version_id,
                    "version": version,
                }
            continue
        if node_type != "script":
            continue
        script_id = config.get("script_id")
        if not script_id or script_id not in latest_versions:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Script node {node['id']} is invalid"
            )
        version_id, version = latest_versions[script_id]
        requested = config.get("version")
        if requested not in (None, "latest", version):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Requested script version not found"
            )
        resolved[node["id"]] = {
            "script_id": script_id,
            "script_version_id": version_id,
            "version": version,
        }
    return resolved
