from copy import deepcopy
from typing import Any

from app.services.english_exam_script import english_exam_answer_filler_template
from app.services.pingcode_worklog_script import pingcode_worklog_template
from app.services.system_info_script import system_info_template

SCRIPT_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "blank",
        "name": "Blank Python",
        "description": "Start with the standard inputs/context contract.",
        "category": "basic",
        "source_files": {"main.py": 'def main(inputs, context):\n    return {"result": inputs}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {"result": {}}, "required": ["result"]},
        "sample_inputs": {},
    },
    {
        "id": "text-cleanup",
        "name": "Text cleanup",
        "description": "Trim whitespace and optionally normalize letter case.",
        "category": "text",
        "source_files": {"main.py": 'def main(inputs, context):\n    text = " ".join(inputs["text"].split())\n    mode = inputs.get("case", "keep")\n    if mode == "lower":\n        text = text.lower()\n    elif mode == "upper":\n        text = text.upper()\n    return {"text": text}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to clean"}, "case": {"type": "string", "enum": ["keep", "lower", "upper"], "default": "keep"}}, "required": ["text"]},
        "output_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
        "sample_inputs": {"text": "  Hello   World  ", "case": "lower"},
    },
    {
        "id": "json-mapper",
        "name": "JSON field mapper",
        "description": "Map selected source fields to new output names.",
        "category": "data",
        "source_files": {"main.py": 'def main(inputs, context):\n    source = inputs["source"]\n    mapping = inputs["mapping"]\n    return {"result": {target: source.get(origin) for target, origin in mapping.items()}}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"source": {"type": "object"}, "mapping": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["source", "mapping"]},
        "output_schema": {"type": "object", "properties": {"result": {"type": "object"}}, "required": ["result"]},
        "sample_inputs": {"source": {"first_name": "Ada"}, "mapping": {"name": "first_name"}},
    },
    {
        "id": "list-filter",
        "name": "List filter",
        "description": "Keep objects whose field equals a configured value.",
        "category": "data",
        "source_files": {"main.py": 'def main(inputs, context):\n    field = inputs["field"]\n    expected = inputs["equals"]\n    items = [item for item in inputs["items"] if isinstance(item, dict) and item.get(field) == expected]\n    return {"items": items, "count": len(items)}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object"}}, "field": {"type": "string"}, "equals": {}}, "required": ["items", "field", "equals"]},
        "output_schema": {"type": "object", "properties": {"items": {"type": "array"}, "count": {"type": "integer"}}, "required": ["items", "count"]},
        "sample_inputs": {"items": [{"active": True}, {"active": False}], "field": "active", "equals": True},
    },
    {
        "id": "regex-extract",
        "name": "Regular expression extractor",
        "description": "Extract named groups from text using the standard library.",
        "category": "text",
        "source_files": {"main.py": 'import re\n\ndef main(inputs, context):\n    match = re.search(inputs["pattern"], inputs["text"])\n    return {"matched": bool(match), "groups": match.groupdict() if match else {}}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["text", "pattern"]},
        "output_schema": {"type": "object", "properties": {"matched": {"type": "boolean"}, "groups": {"type": "object"}}, "required": ["matched", "groups"]},
        "sample_inputs": {"text": "order-42", "pattern": "order-(?P<id>\\d+)"},
    },
    {
        "id": "date-normalizer",
        "name": "Date normalizer",
        "description": "Convert an ISO timestamp to UTC.",
        "category": "data",
        "source_files": {"main.py": 'from datetime import UTC, datetime\n\ndef main(inputs, context):\n    value = datetime.fromisoformat(inputs["value"].replace("Z", "+00:00"))\n    return {"value": value.astimezone(UTC).isoformat().replace("+00:00", "Z")}\n'},
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"value": {"type": "string", "format": "date-time"}}, "required": ["value"]},
        "output_schema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
        "sample_inputs": {"value": "2026-01-01T08:00:00+08:00"},
    },
    {
        "id": "agent-tool",
        "name": "Agent tool (multi-file)",
        "description": "A multi-file tool template that demonstrates package imports.",
        "category": "agent",
        "source_files": {
            "main.py": 'from helpers.text import summarize\n\ndef main(inputs, context):\n    return {"summary": summarize(inputs["text"], inputs.get("max_length", 120))}\n',
            "helpers/__init__.py": "",
            "helpers/text.py": 'def summarize(text, max_length):\n    value = " ".join(text.split())\n    return value if len(value) <= max_length else value[:max_length - 3] + "..."\n',
        },
        "entrypoint": "main:main",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to summarize"}, "max_length": {"type": "integer", "minimum": 10, "default": 120}}, "required": ["text"]},
        "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False},
        "sample_inputs": {"text": "A long piece of text for the agent tool.", "max_length": 40},
    },
    english_exam_answer_filler_template(),
    pingcode_worklog_template(),
    system_info_template(),
]


def list_script_templates() -> list[dict[str, Any]]:
    return deepcopy(SCRIPT_TEMPLATES)
