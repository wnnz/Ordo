from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ScriptVersion


async def _load_version(
    db: AsyncSession, script_id: str, version_id: str | None
) -> ScriptVersion | None:
    if version_id:
        version = await db.get(ScriptVersion, version_id)
        if version and version.script_id == script_id:
            return version
    return await db.scalar(
        select(ScriptVersion)
        .where(ScriptVersion.script_id == script_id)
        .order_by(ScriptVersion.version.desc())
        .limit(1)
    )


def _runtime(version: ScriptVersion) -> dict[str, Any]:
    return {
        "source": version.source_code,
        "source_files": version.source_files or {"main.py": version.source_code},
        "entrypoint": version.entrypoint,
        "input_schema": version.input_schema,
        "output_schema": version.output_schema,
        "network_enabled": version.network_enabled,
    }


async def hydrate_script_resources(
    db: AsyncSession,
    graph: dict[str, Any],
    references: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hydrated = deepcopy(graph)
    refs = references or {}
    for node in hydrated.get("nodes", []):
        config = node.get("data", {}).get("config", {})
        if node.get("type") == "script":
            script_id = str(config.get("script_id", ""))
            reference = refs.get(str(node.get("id")), {})
            version = await _load_version(db, script_id, reference.get("script_version_id"))
            if version:
                config["_script_runtime"] = _runtime(version)
        elif node.get("type") == "agent":
            for tool in config.get("tools", []):
                if tool.get("type") != "script" or not tool.get("enabled", True):
                    continue
                script_id = str(tool.get("reference_id", ""))
                key = f"{node.get('id')}:{tool.get('id') or script_id}"
                version = await _load_version(
                    db, script_id, refs.get(key, {}).get("script_version_id")
                )
                if version:
                    tool["_script_runtime"] = _runtime(version)
                    tool["parameters"] = version.input_schema
        child_graph = config.get("_resolved_graph")
        if isinstance(child_graph, dict):
            config["_resolved_graph"] = await hydrate_script_resources(db, child_graph)
    return hydrated
