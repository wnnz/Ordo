from __future__ import annotations

from typing import Any

from app.services.english_exam_script import (
    ENGLISH_EXAM_ANSWER_FILLER_INPUT_SCHEMA,
    ENGLISH_EXAM_ANSWER_FILLER_NAME,
    ENGLISH_EXAM_ANSWER_FILLER_OUTPUT_SCHEMA,
)
from app.services.system_info_script import SYSTEM_INFO_NAME

ENGLISH_EXAM_TEMPLATE_ID = "english_exam_answer_filler"
SYSTEM_INFO_WORKFLOW_TEMPLATE_ID = "system_info"
RDP_DISCONNECT_WORKFLOW_TEMPLATE_ID = "rdp_disconnect"

CHAT_SYSTEM_PROMPT = "You are a helpful assistant."


def build_chat_graph(*, provider_id: str = "", model: str = "") -> dict[str, Any]:
    nodes = [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 60, "y": 180},
            "data": {
                "label": "Start",
                "config": {
                    "triggers": ["form"],
                    "input_fields": [
                        {
                            "name": "message",
                            "label": "Message",
                            "type": "text",
                            "required": True,
                            "placeholder": "",
                            "default_value": "",
                            "max_length": 2000,
                        }
                    ],
                    "schedule": {
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                        "enabled": False,
                        "inputs_json": "{}",
                    },
                },
            },
        },
        {
            "id": "llm",
            "type": "llm",
            "position": {"x": 380, "y": 180},
            "data": {
                "label": "LLM",
                "description": "Generate a reply to the user's message",
                "config": {
                    "provider_id": provider_id,
                    "model": model,
                    "temperature": 0.7,
                    "top_p": 1,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                        {"role": "user", "content": "{{inputs.message}}"},
                    ],
                    "prompt": "",
                    "context": "",
                    "vision": {"enabled": False, "variable": "", "detail": "high"},
                    "reasoning": {"separate": False},
                    "response_format": "text",
                    "response_schema": {"type": "object", "properties": {}},
                    "retry": {"enabled": False, "max_retries": 3, "interval_seconds": 0},
                    "error_strategy": "fail",
                    "default_output": {},
                },
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 700, "y": 180},
            "data": {
                "label": "End",
                "config": {
                    "outputs": [{"name": "message", "type": "String", "value": "{{LLM.text}}"}]
                },
            },
        },
    ]
    edges = [
        {"id": "start-llm", "source": "start", "target": "llm"},
        {"id": "llm-end", "source": "llm", "target": "end"},
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def build_system_info_graph() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 60, "y": 180}, "data": {"label": "获取本机信息", "config": {"triggers": ["form"], "input_fields": [], "schedule": {"cron": "0 9 * * *", "timezone": "UTC", "enabled": False, "inputs_json": "{}"}}}},
            {"id": "collect", "type": "host_info", "position": {"x": 420, "y": 180}, "data": {"label": SYSTEM_INFO_NAME, "description": "通过受保护的 Windows Agent 读取物理机网卡地址", "config": {"timeout_seconds": 10}}},
            {"id": "end", "type": "end", "position": {"x": 780, "y": 180}, "data": {"label": "返回信息", "config": {"outputs": [{"name": "primary_ipv4", "type": "String", "value": "{{本机信息.primary_ipv4}}"}, {"name": "primary_interface", "type": "String", "value": "{{本机信息.primary_interface}}"}, {"name": "adapters", "type": "Array", "value": "{{本机信息.adapters}}"}, {"name": "source", "type": "String", "value": "{{本机信息.source}}"}]}}},
        ],
        "edges": [{"id": "start-collect", "source": "start", "target": "collect"}, {"id": "collect-end", "source": "collect", "target": "end"}],
    }


def build_rdp_disconnect_graph() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 60, "y": 180},
                "data": {
                    "label": "手动触发",
                    "config": {
                        "triggers": ["form"],
                        "input_fields": [],
                        "schedule": {
                            "cron": "0 9 * * *",
                            "timezone": "Asia/Singapore",
                            "enabled": False,
                            "inputs_json": "{}",
                        },
                    },
                },
            },
            {
                "id": "disconnect-rdp",
                "type": "rdp_disconnect",
                "position": {"x": 420, "y": 180},
                "data": {
                    "label": "断开远程桌面",
                    "description": "断开当前活跃的 RDP 会话，不注销用户或结束其程序",
                    "config": {"timeout_seconds": 10},
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 780, "y": 180},
                "data": {
                    "label": "返回结果",
                    "config": {
                        "outputs": [
                            {
                                "name": "ok",
                                "type": "Boolean",
                                "value": "{{断开远程桌面.ok}}",
                            },
                            {
                                "name": "disconnected_count",
                                "type": "Number",
                                "value": "{{断开远程桌面.disconnected_count}}",
                            },
                            {
                                "name": "sessions",
                                "type": "Array",
                                "value": "{{断开远程桌面.sessions}}",
                            },
                            {
                                "name": "message",
                                "type": "String",
                                "value": "{{断开远程桌面.message}}",
                            },
                        ]
                    },
                },
            },
        ],
        "edges": [
            {"id": "start-disconnect", "source": "start", "target": "disconnect-rdp"},
            {"id": "disconnect-end", "source": "disconnect-rdp", "target": "end"},
        ],
    }


ENGLISH_EXAM_SYSTEM_PROMPT = """你是一名专业的英语教师和文档结构分析专家。

请分析从英语练习文档中提取出的完整文本和随附图片。文档的版式、标题和编号方式可能不固定。你需要识别文档层级，只完成非听力题，并为每个可作答的“答案汇总单元”生成一个答案块，插入到该单元最后一道小题之后。

只能输出合法 JSON，格式必须严格如下：
{"insertions":[{"question_number":"Part 2 - Task 1","anchor_id":"P0012","anchor":"该答案汇总单元最后一个原文段落中除段落编号和图片标记外的精确文本","answer":"该单元全部小题的答案"}]}

规则：
1. 根据标题层级、编号、题目说明、版式分隔、主题变化和上下文识别结构，不要依赖 Part、Task 等任何固定名称。
2. “答案汇总单元”是包含实际小题、需要共享一个答案块的最深层有效分组。它可能叫 Task、Section、Exercise、Activity、Passage、Dialogue、Reading、Round、A/B/C，或没有明确名称。
3. 如果 Part、大题或其他父级标题下面还有一个或多个各自包含小题的子分组，父级只作为容器：必须为每个子分组分别生成 insertion，不能把答案合并到父级末尾。
4. 如果某个大题下面没有这种子分组，则该大题自身就是答案汇总单元。不要把同一单元内普通的 1、2、3 等小题拆成多个 insertion。
5. 如果存在更多嵌套层级，选择直接包含实际小题的最深层合理分组；同一小题只能属于一个答案汇总单元，不能重复作答。
6. 必须识别听力题及其所属单元，不依赖固定标题。判断依据包括但不限于 Listening、听力、Listen and、录音、音频、播放、you will hear、recording、audio、track 等标题或作答说明。
7. 当前没有提供模型可读取的音频。所有依赖音频内容才能作答的听力单元必须从 insertions 中完全省略；严禁根据选项、常识、图片、题号规律或相邻文字猜测听力答案，也不要插入“无法作答”“未提供音频”等占位答案。
8. 如果同一父级下同时包含听力和非听力子单元，只跳过听力单元，其他单元照常作答。如果整份文档没有任何可作答的非听力单元，必须只输出 {"insertions":[]}。
9. 只有当题目明确提供了完整文字材料、无需听取音频也能独立作答时，才可将其视为非听力题；仅有题干、选项或不完整的听力原文，不足以作答。
10. 每个原文段落前都有 [P0001] 格式的稳定编号。anchor_id 必须填写当前答案汇总单元最后一道小题（含选项、材料或图片）的最后一个原文段落编号，不能填写下一个单元的标题。包括只有图片的段落。anchor 复制该段落中除 [Pxxxx] 和 [图片 N] 外的原文；没有文字时允许为空字符串。
11. 每个 answer 只包含当前答案汇总单元的全部小题答案，按原小题顺序编号并用换行分隔。question_number 使用能够唯一识别该单元的层级名称。
12. 准确完成题目。除非题目明确要求解释、作文、翻译或完整句子，否则只给出答案。
13. 文本中的“[图片 N]”与视觉输入中的第 N 张图片对应。必须阅读图片中的文字、图表、示意图和选项，并结合图片所在段落作答。
14. 如果题目不依赖图片，按普通文字题处理。不要猜测无法看清的图片内容；确实无法辨认时，在答案中明确说明。
15. insertions 必须按单元在原文中的顺序排列。不要输出 Markdown 代码块，也不要在 JSON 外添加说明。

提取出的文档全文：
{{提取试卷.content}}"""

ANSWER_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "insertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_number": {"type": "string"},
                    "anchor_id": {"type": "string"},
                    "anchor": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question_number", "anchor_id", "anchor", "answer"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["insertions"],
    "additionalProperties": False,
}


def build_english_exam_graph(
    *,
    provider_id: str,
    model: str,
    vision_enabled: bool,
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
            "position": {"x": 60, "y": 180},
            "data": {
                "label": "上传英语试卷",
                "config": {
                    "triggers": ["form"],
                    "input_fields": [
                        {
                            "name": "exam_file",
                            "label": "英语试卷 Word 文件",
                            "type": "file",
                            "required": True,
                            "placeholder": "上传 .docx 文件",
                            "default_value": "",
                            "max_length": None,
                        }
                    ],
                    "schedule": {
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                        "enabled": False,
                        "inputs_json": "{}",
                    },
                },
            },
        },
        {
            "id": "extract-docx",
            "type": "document",
            "position": {"x": 380, "y": 180},
            "data": {
                "label": "提取试卷",
                "description": "读取 DOCX 文本并生成稳定段落锚点",
                "config": {
                    "operation": "extract",
                    "source": "{{上传英语试卷.exam_file}}",
                    "extract_mode": "text_images" if vision_enabled else "text",
                    "page_range": "",
                    "ocr_fallback": False,
                    **policy,
                },
            },
        },
        {
            "id": "answer-exam",
            "type": "llm",
            "position": {"x": 700, "y": 180},
            "data": {
                "label": "解析题目并作答",
                "description": "跳过听力题，按试卷最深层有效分组生成答案方案",
                "config": {
                    "provider_id": provider_id,
                    "model": model,
                    "temperature": 0.1,
                    "top_p": 1,
                    "max_tokens": 16_000,
                    "messages": [
                        {"role": "system", "content": ENGLISH_EXAM_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": "请解析完整文档，跳过所有依赖音频的听力题，只对可独立作答的非听力题按最深层有效分组作答，并严格按照指定 JSON 格式输出结果。",
                        },
                    ],
                    "prompt": "",
                    "context": "",
                    "vision": {
                        "enabled": vision_enabled,
                        "variable": "{{提取试卷.images}}" if vision_enabled else "",
                        "detail": "high",
                    },
                    "reasoning": {"separate": False},
                    "response_format": "json_schema",
                    "response_schema": ANSWER_PLAN_SCHEMA,
                    **policy,
                },
            },
        },
        {
            "id": "fill-answers",
            "type": "script",
            "position": {"x": 1020, "y": 180},
            "data": {
                "label": "填充答案",
                "description": "在原试卷中按段落锚点插入红色答案",
                "config": {
                    "script_id": script_id,
                    "script_name": ENGLISH_EXAM_ANSWER_FILLER_NAME,
                    "version": script_version,
                    "inputs": {
                        "source": "{{上传英语试卷.exam_file}}",
                        "answers": "{{解析题目并作答.structured_output}}",
                        "output_name": "{{上传英语试卷.exam_file.stem}}_已作答.docx",
                    },
                    "input_schema": ENGLISH_EXAM_ANSWER_FILLER_INPUT_SCHEMA,
                    "output_schema": ENGLISH_EXAM_ANSWER_FILLER_OUTPUT_SCHEMA,
                    **policy,
                },
            },
        },
        {
            "id": "end",
            "type": "end",
            "position": {"x": 1340, "y": 180},
            "data": {
                "label": "返回已作答试卷",
                "config": {
                    "outputs": [
                        {"name": "file", "type": "File", "value": "{{填充答案.file}}"},
                        {
                            "name": "inserted_count",
                            "type": "Number",
                            "value": "{{填充答案.inserted_count}}",
                        },
                        {
                            "name": "insertions",
                            "type": "Array",
                            "value": "{{填充答案.insertions}}",
                        },
                    ]
                },
            },
        },
    ]
    edges = [
        {"id": "start-extract", "source": "start", "target": "extract-docx"},
        {"id": "extract-answer", "source": "extract-docx", "target": "answer-exam"},
        {"id": "answer-fill", "source": "answer-exam", "target": "fill-answers"},
        {"id": "fill-end", "source": "fill-answers", "target": "end"},
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges}
