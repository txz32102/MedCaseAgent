from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


ToolFunction = Callable[..., Any]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    schema: dict[str, Any]
    function: ToolFunction
    skill_name: str
    path: Path


class ToolLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._tools = self._discover()

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, name: str, arguments: dict[str, Any], context: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Tool '{name}' is not registered."})

        try:
            result = tool.function(**dict(arguments), context=context)
        except TypeError:
            try:
                result = tool.function(**dict(arguments))
            except Exception as exc:
                result = {"error": f"Error executing {name}: {exc}"}
        except Exception as exc:
            result = {"error": f"Error executing {name}: {exc}"}
        return _stringify_tool_result(result)

    def _discover(self) -> dict[str, RegisteredTool]:
        tools: dict[str, RegisteredTool] = {}
        if not self.root.exists():
            return tools

        for tool_file in sorted(self.root.glob("*/tools.py")):
            module = _load_tool_module(tool_file)
            schemas = getattr(module, "TOOL_SCHEMAS", [])
            functions = getattr(module, "AVAILABLE_TOOLS", {})
            if not isinstance(schemas, list) or not isinstance(functions, dict):
                continue

            for schema in schemas:
                name = _schema_name(schema)
                function = functions.get(name)
                if not name or not callable(function):
                    continue
                tools[name] = RegisteredTool(
                    name=name,
                    schema=schema,
                    function=function,
                    skill_name=tool_file.parent.name,
                    path=tool_file,
                )
        return tools


def _load_tool_module(path: Path) -> ModuleType:
    module_name = f"medcase_skill_tools_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_name(schema: dict[str, Any]) -> str:
    function = schema.get("function")
    if not isinstance(function, dict):
        return ""
    name = function.get("name")
    return str(name) if name else ""


def _stringify_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2)
