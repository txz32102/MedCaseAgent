from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path
    when_to_use: str = ""

    def render(self) -> str:
        header = f"## Skill: {self.name}\nDescription: {self.description}".strip()
        return f"{header}\n\n{self.body.strip()}"


class SkillLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._skills = self._discover()

    def render(self, names: list[str]) -> str:
        missing = [name for name in names if name not in self._skills]
        if missing:
            raise KeyError(f"Missing skills: {', '.join(missing)}")
        return "\n\n".join(self._skills[name].render() for name in names)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def _discover(self) -> dict[str, Skill]:
        skills: dict[str, Skill] = {}
        if not self.root.exists():
            return skills
        for skill_file in sorted(self.root.glob("*/SKILL.md")):
            skill = _parse_skill(skill_file)
            skills[skill.name] = skill
        return skills


def _parse_skill(path: Path) -> Skill:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw
    if raw.startswith("---"):
        _, frontmatter, body = raw.split("---", 2)
        meta = yaml.safe_load(frontmatter) or {}

    return Skill(
        name=str(meta.get("name") or path.parent.name),
        description=str(meta.get("description") or ""),
        when_to_use=str(meta.get("when_to_use") or meta.get("when-to-use") or ""),
        body=body,
        path=path,
    )
