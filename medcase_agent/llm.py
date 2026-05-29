from __future__ import annotations

import base64
import json
from typing import Any, Callable

from openai import OpenAI

from .config import Settings
from .models import ImageAsset, StageResult


ToolExecutor = Callable[[str, dict[str, Any], dict[str, Any]], str]
StreamWriter = Callable[[str], None]


class LLM:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env.")
        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    def run(
        self,
        stage: str,
        instructions: str,
        prompt: str,
        images: list[ImageAsset] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_context: dict[str, Any] | None = None,
        tool_executor: ToolExecutor | None = None,
        stream_writer: StreamWriter | None = None,
    ) -> StageResult:
        return self._run_chat(
            stage,
            instructions,
            prompt,
            images or [],
            tools or [],
            tool_context or {},
            tool_executor,
            stream_writer,
        )

    def _run_chat(
        self,
        stage: str,
        instructions: str,
        prompt: str,
        images: list[ImageAsset],
        tools: list[dict[str, Any]],
        tool_context: dict[str, Any],
        tool_executor: ToolExecutor | None,
        stream_writer: StreamWriter | None,
    ) -> StageResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": _chat_content(prompt, images)},
        ]
        usage_items: list[dict[str, Any]] = []
        tool_log: list[dict[str, Any]] = []
        last_response_id: str | None = None
        max_tool_turns = self.settings.max_tool_turns if tools else 0

        for turn in range(max_tool_turns + 1):
            active_tools = tools if turn < max_tool_turns else []
            kwargs: dict[str, Any] = {
                "model": self.settings.model,
                "messages": messages,
                "store": False,
            }
            if active_tools:
                kwargs["tools"] = active_tools
                kwargs["tool_choice"] = "auto"
            if self.settings.reasoning_effort:
                kwargs["reasoning_effort"] = self.settings.reasoning_effort

            if stream_writer is None:
                response = self.client.chat.completions.create(**kwargs)
                last_response_id = getattr(response, "id", None)
                usage_items.append(_usage(response))

                message = response.choices[0].message if response.choices else None
                if message is None:
                    break
                content = message.content or ""
                tool_calls = list(getattr(message, "tool_calls", None) or [])
                assistant_message = _message_dict(message)
            else:
                streamed = self._stream_completion(kwargs, stream_writer)
                last_response_id = streamed["response_id"] or last_response_id
                if streamed["usage"]:
                    usage_items.append(streamed["usage"])
                content = streamed["content"]
                tool_calls = streamed["tool_calls"]
                assistant_message = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                }

            if not tool_calls:
                return StageResult(
                    name=stage,
                    output=content.strip(),
                    response_id=last_response_id,
                    usage=_combine_usage(usage_items),
                    tool_calls=tool_log,
                )

            messages.append(assistant_message)
            for tool_call in tool_calls:
                function_name = _tool_call_function_name(tool_call)
                arguments_text = _tool_call_function_arguments(tool_call) or "{}"
                log_entry: dict[str, Any] = {
                    "turn": turn + 1,
                    "name": function_name,
                    "arguments": None,
                    "result": None,
                    "error": None,
                }
                try:
                    arguments = json.loads(arguments_text)
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must decode to a JSON object.")
                    log_entry["arguments"] = arguments
                    if tool_executor is None:
                        raise RuntimeError("Tool executor is not configured.")
                    tool_result = tool_executor(function_name, arguments, tool_context)
                    log_entry["result"] = tool_result
                except Exception as exc:
                    tool_result = json.dumps({"error": str(exc)})
                    log_entry["error"] = str(exc)

                tool_log.append(log_entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _tool_call_id(tool_call),
                        "name": function_name,
                        "content": tool_result,
                    }
                )

        return StageResult(
            name=stage,
            output="",
            response_id=last_response_id,
            usage=_combine_usage(usage_items),
            tool_calls=tool_log,
        )

    def _stream_completion(
        self,
        kwargs: dict[str, Any],
        stream_writer: StreamWriter,
    ) -> dict[str, Any]:
        content_parts: list[str] = []
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        response_id: str | None = None
        usage: dict[str, Any] = {}

        stream = self.client.chat.completions.create(**kwargs, stream=True)
        for chunk in stream:
            response_id = getattr(chunk, "id", None) or response_id
            chunk_usage = _usage(chunk)
            if chunk_usage:
                usage = chunk_usage

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue

            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue

            content = getattr(delta, "content", None)
            if content:
                content_parts.append(content)
                stream_writer(content)

            for tool_call_delta in getattr(delta, "tool_calls", None) or []:
                _merge_tool_call_delta(tool_calls_by_index, tool_call_delta)

        return {
            "content": "".join(content_parts),
            "tool_calls": [
                tool_call
                for _, tool_call in sorted(tool_calls_by_index.items(), key=lambda item: item[0])
            ],
            "response_id": response_id,
            "usage": usage,
        }


def _chat_content(prompt: str, images: list[ImageAsset]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_url(image), "detail": "high"},
            }
        )
    return content


def _data_url(image: ImageAsset) -> str:
    raw = image.path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{image.mime_type};base64,{encoded}"


def _usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    return dict(usage)


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return dict(message)


def _tool_call_id(tool_call: Any) -> str:
    if isinstance(tool_call, dict):
        return str(tool_call.get("id") or "")
    return str(getattr(tool_call, "id", "") or "")


def _tool_call_function_name(tool_call: Any) -> str:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return str(getattr(function, "name", "") or "")


def _tool_call_function_arguments(tool_call: Any) -> str:
    function = tool_call.get("function") if isinstance(tool_call, dict) else getattr(tool_call, "function", None)
    if isinstance(function, dict):
        return str(function.get("arguments") or "")
    return str(getattr(function, "arguments", "") or "")


def _merge_tool_call_delta(
    tool_calls_by_index: dict[int, dict[str, Any]],
    tool_call_delta: Any,
) -> None:
    index = getattr(tool_call_delta, "index", None)
    if index is None:
        index = len(tool_calls_by_index)

    current = tool_calls_by_index.setdefault(
        int(index),
        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
    )

    tool_call_id = getattr(tool_call_delta, "id", None)
    if tool_call_id:
        current["id"] = tool_call_id

    tool_call_type = getattr(tool_call_delta, "type", None)
    if tool_call_type:
        current["type"] = tool_call_type

    function = getattr(tool_call_delta, "function", None)
    if function is None:
        return

    name = getattr(function, "name", None)
    if name:
        current["function"]["name"] += name

    arguments = getattr(function, "arguments", None)
    if arguments:
        current["function"]["arguments"] += arguments


def _combine_usage(items: list[dict[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, (int, float)):
                combined[key] = combined.get(key, 0) + value
    if len(items) > 1:
        combined["calls"] = items
    return combined
