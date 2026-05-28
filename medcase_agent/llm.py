from __future__ import annotations

import base64
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import ImageAsset, StageResult


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
    ) -> StageResult:
        return self._run_chat(stage, instructions, prompt, images or [])

    def _run_chat(
        self,
        stage: str,
        instructions: str,
        prompt: str,
        images: list[ImageAsset],
    ) -> StageResult:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": _chat_content(prompt, images)},
            ],
            "store": False,
        }
        if self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message if response.choices else None
        return StageResult(
            name=stage,
            output=(message.content or "").strip() if message else "",
            response_id=getattr(response, "id", None),
            usage=_usage(response),
        )


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
