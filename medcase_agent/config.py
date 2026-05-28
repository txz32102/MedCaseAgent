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
    enable_tools: bool
    max_tool_turns: int
    curate_citations: bool
    target_references: int

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
            enable_tools=_bool_env(os.getenv("MEDCASE_ENABLE_TOOLS"), default=True),
            max_tool_turns=_int_env(os.getenv("MEDCASE_MAX_TOOL_TURNS"), default=8),
            curate_citations=_bool_env(os.getenv("MEDCASE_CURATE_CITATIONS"), default=True),
            target_references=_int_env(os.getenv("MEDCASE_TARGET_REFERENCES"), default=10),
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


def _bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("Boolean environment values must be true/false, yes/no, on/off, or 1/0.")


def _int_env(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    parsed = int(value)
    if parsed < 0:
        raise ValueError("MEDCASE_MAX_TOOL_TURNS must be 0 or greater.")
    return parsed
