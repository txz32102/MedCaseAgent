from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    model: str
    reasoning_effort: str | None
    output_dir: Path

    @classmethod
    def load(
        cls,
        env_file: Path | None = None,
        output_dir: Path | None = None,
        require_key: bool = True,
    ) -> "Settings":
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=True)
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ZXMMM_API_KEY") or None
        if require_key and not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env.")

        raw_output_dir = output_dir or Path(os.getenv("MEDCASE_OUTPUT_DIR", "runs"))
        if not raw_output_dir.is_absolute():
            raw_output_dir = PROJECT_ROOT / raw_output_dir

        return cls(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            reasoning_effort=_reasoning_effort(os.getenv("OPENAI_REASONING_EFFORT")),
            output_dir=raw_output_dir,
        )


def _reasoning_effort(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    aliases = {
        "med": "medium",
        "mid": "medium",
        "max": "xhigh",
        "maximum": "xhigh",
        "x-high": "xhigh",
        "extra_high": "xhigh",
    }
    normalized = aliases.get(normalized, normalized)
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    if normalized not in allowed:
        raise ValueError(
            "OPENAI_REASONING_EFFORT must be one of: none, minimal, low, medium, high, xhigh."
        )
    return normalized
