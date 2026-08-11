from __future__ import annotations

from pathlib import Path

SYSTEM_INFO_TEMPLATE_ID = "system-info"
SYSTEM_INFO_SLUG = "system-info"
SYSTEM_INFO_NAME = "本机信息"
SYSTEM_INFO_DESCRIPTION = "读取 Ordo 执行环境的系统、资源和网络接口摘要，不执行用户提供的命令。"
SYSTEM_INFO_SOURCE = (
    Path(__file__).parents[1]
    .joinpath("script_sources", "system_info.py")
    .read_text(encoding="utf-8")
)
SYSTEM_INFO_INPUT_SCHEMA = {"type": "object", "properties": {}}
SYSTEM_INFO_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "object"},
        "resources": {"type": "object"},
        "network": {"type": "object"},
        "ipconfig": {"type": "string"},
    },
    "required": ["platform", "resources", "network", "ipconfig"],
    "additionalProperties": False,
}


def system_info_template() -> dict:
    return {
        "id": SYSTEM_INFO_TEMPLATE_ID,
        "name": SYSTEM_INFO_NAME,
        "description": SYSTEM_INFO_DESCRIPTION,
        "category": "system",
        "source_files": {"main.py": SYSTEM_INFO_SOURCE},
        "entrypoint": "main:main",
        "input_schema": SYSTEM_INFO_INPUT_SCHEMA,
        "output_schema": SYSTEM_INFO_OUTPUT_SCHEMA,
        "sample_inputs": {},
    }
