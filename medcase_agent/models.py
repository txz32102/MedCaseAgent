from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImageAsset:
    ref: str
    path: Path
    mime_type: str
    output_name: str


@dataclass(frozen=True)
class ClinicalCase:
    case_id: str
    source_path: Path
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    images: list[ImageAsset] = field(default_factory=list)

    def image_index(self) -> str:
        if not self.images:
            return "No supported images found."
        return "\n".join(
            f"- {image.ref}: {image.path.name} -> images/{image.output_name} "
            f"(embed as `![Figure n](images/{image.output_name})`)"
            for image in self.images
        )


@dataclass(frozen=True)
class StageResult:
    name: str
    output: str
    response_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
