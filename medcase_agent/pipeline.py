from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, Settings
from .data import load_case
from .llm import LLM
from .models import ClinicalCase, StageResult
from .prompts import instructions, planner_prompt, refiner_prompt, writer_prompt
from .skills import SkillLibrary


STAGE_SKILLS = {
    "planner": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
    ],
    "writer": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
    ],
    "refiner": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
        "final_audit",
    ],
}


class MedCaseAgent:
    def __init__(
        self,
        settings: Settings,
        skill_dir: Path | None = None,
        llm: LLM | None = None,
    ):
        self.settings = settings
        self.skills = SkillLibrary(skill_dir or PROJECT_ROOT / "skills")
        self.llm = llm or LLM(settings)

    def run_case(self, case_path: Path) -> Path:
        case = load_case(case_path)
        run_dir = self._run_dir(case)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._copy_images(case, run_dir)

        planner = self._stage("planner", planner_prompt(case), case)
        self._write_stage(run_dir, 1, planner)

        writer = self._stage("writer", writer_prompt(case, planner.output), case)
        self._write_stage(run_dir, 2, writer)

        refiner = self._stage(
            "refiner",
            refiner_prompt(case, planner.output, writer.output),
            case,
        )
        self._write_stage(run_dir, 3, refiner)

        final_path = run_dir / "final.md"
        final_path.write_text(refiner.output.strip() + "\n", encoding="utf-8")
        self._write_log(run_dir, case, [planner, writer, refiner])
        return final_path

    def _stage(self, name: str, prompt: str, case: ClinicalCase) -> StageResult:
        skill_text = self.skills.render(STAGE_SKILLS[name])
        return self.llm.run(
            stage=name,
            instructions=instructions(name, skill_text),
            prompt=prompt,
            images=case.images,
        )

    def _run_dir(self, case: ClinicalCase) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.settings.output_dir / f"{case.case_id}_{stamp}"

    def _copy_images(self, case: ClinicalCase, run_dir: Path) -> None:
        if not case.images:
            return
        image_dir = run_dir / "images"
        image_dir.mkdir(exist_ok=True)
        for image in case.images:
            shutil.copy2(image.path, image_dir / image.output_name)

    def _write_stage(self, run_dir: Path, index: int, result: StageResult) -> None:
        path = run_dir / f"{index:02d}_{result.name}.md"
        path.write_text(result.output.strip() + "\n", encoding="utf-8")

    def _write_log(
        self,
        run_dir: Path,
        case: ClinicalCase,
        results: list[StageResult],
    ) -> None:
        log: dict[str, Any] = {
            "case_id": case.case_id,
            "source_path": str(case.source_path),
            "model": self.settings.model,
            "base_url": self.settings.base_url,
            "skills": self.skills.names(),
            "images": [
                {
                    "ref": image.ref,
                    "source": str(image.path),
                    "output": f"images/{image.output_name}",
                }
                for image in case.images
            ],
            "stages": [
                {
                    "name": result.name,
                    "response_id": result.response_id,
                    "usage": result.usage,
                }
                for result in results
            ],
        }
        (run_dir / "run_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
