from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import PROJECT_ROOT, Settings
from .data import load_case
from .llm import LLM
from .models import ClinicalCase, StageResult
from .prompts import instructions, planner_prompt, refiner_prompt, writer_prompt
from .skills import SkillLibrary
from .tools import ToolLibrary

StreamWriter = Callable[[str], None]


STAGE_SKILLS = {
    "planner": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
        "tool_use_policy",
    ],
    "writer": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
        "tool_use_policy",
    ],
    "refiner": [
        "clinical_fidelity",
        "care_case_report",
        "visual_reporting",
        "citation_policy",
        "tool_use_policy",
        "final_audit",
    ],
}


class MedCaseAgent:
    def __init__(
        self,
        settings: Settings,
        skill_dir: Path | None = None,
        llm: LLM | None = None,
        stream: bool = False,
        stream_writer: StreamWriter | None = None,
    ):
        self.settings = settings
        self.skill_dir = skill_dir or PROJECT_ROOT / "skills"
        self.skills = SkillLibrary(self.skill_dir)
        self.tools = ToolLibrary(self.skill_dir)
        self.llm = llm or LLM(settings)
        self.stream = stream
        self.stream_writer = stream_writer

    def run_case(self, case_path: Path) -> Path:
        case = load_case(case_path)
        run_dir = self._run_dir(case)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._copy_images(case, run_dir)
        self._emit(f"run_dir={run_dir}\n")

        self._emit("stage=citation_curator status=running\n")
        citation_curator = self._curate_citations(case)
        if citation_curator.output:
            self._write_stage(run_dir, 0, citation_curator)
        self._emit("stage=citation_curator status=done\n")

        planner = self._stage("planner", planner_prompt(case, citation_curator.output), case)
        self._write_stage(run_dir, 1, planner)

        writer = self._stage(
            "writer",
            writer_prompt(case, planner.output, citation_curator.output),
            case,
        )
        self._write_stage(run_dir, 2, writer)

        refiner = self._stage(
            "refiner",
            refiner_prompt(case, planner.output, writer.output, citation_curator.output),
            case,
        )
        self._write_stage(run_dir, 3, refiner)

        final_path = run_dir / "final.md"
        final_path.write_text(refiner.output.strip() + "\n", encoding="utf-8")
        self._write_log(run_dir, case, [citation_curator, planner, writer, refiner])
        return final_path

    def _curate_citations(self, case: ClinicalCase) -> StageResult:
        if not self.settings.enable_tools or not self.settings.curate_citations:
            return StageResult(name="citation_curator", output="")
        if "search_pubmed" not in self.tools.names() or "fetch_ama_citations" not in self.tools.names():
            return StageResult(name="citation_curator", output="")

        context = {
            "case_id": case.case_id,
            "metadata": case.metadata,
            "source_path": str(case.source_path),
        }
        tool_calls: list[dict[str, Any]] = []
        dois: list[str] = []

        for query in _citation_queries(case):
            if len(dois) >= self.settings.target_references:
                break
            args = {"query": query, "max_results": 8}
            result = self.tools.execute("search_pubmed", args, context)
            tool_calls.append(
                {
                    "turn": 1,
                    "name": "search_pubmed",
                    "arguments": args,
                    "result": result,
                    "error": None,
                }
            )
            for doi in _extract_dois(result):
                if doi not in dois:
                    dois.append(doi)
                if len(dois) >= self.settings.target_references:
                    break

        if not dois:
            output = "No DOI-bearing PubMed references were found by the citation curator."
            return StageResult(name="citation_curator", output=output, tool_calls=tool_calls)

        selected_dois = dois[: self.settings.target_references]
        args = {"dois": selected_dois}
        citation_result = self.tools.execute("fetch_ama_citations", args, context)
        tool_calls.append(
            {
                "turn": 1,
                "name": "fetch_ama_citations",
                "arguments": args,
                "result": citation_result,
                "error": None,
            }
        )
        output = (
            "Use these verified references only when clinically relevant. Do not cite "
            "uncited search results or invent reference details.\n\n"
            "## AMA References From DOI Tool\n"
            f"{citation_result}\n\n"
            "## Selected DOI Values\n"
            + "\n".join(f"- {doi}" for doi in selected_dois)
        )
        return StageResult(name="citation_curator", output=output, tool_calls=tool_calls)

    def _stage(self, name: str, prompt: str, case: ClinicalCase) -> StageResult:
        active_skills = STAGE_SKILLS[name]
        skill_text = self.skills.render(active_skills)
        tools = self.tools.schemas() if self.settings.enable_tools else []
        self._emit(f"\n--- {name} ---\n")
        result = self.llm.run(
            stage=name,
            instructions=instructions(name, skill_text),
            prompt=prompt,
            images=case.images,
            tools=tools,
            tool_context={
                "case_id": case.case_id,
                "metadata": case.metadata,
                "source_path": str(case.source_path),
            },
            tool_executor=self.tools.execute,
            stream_writer=self.stream_writer if self.stream else None,
        )
        self._emit(f"\n--- end {name} ---\n")
        return result

    def _emit(self, text: str) -> None:
        if self.stream and self.stream_writer is not None:
            self.stream_writer(text)

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
            "tools_enabled": self.settings.enable_tools,
            "tools": self.tools.names() if self.settings.enable_tools else [],
            "skills": {
                "available": self.skills.names(),
                "active_by_stage": STAGE_SKILLS,
            },
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
                    "tool_calls": result.tool_calls,
                }
                for result in results
            ],
        }
        (run_dir / "run_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _citation_queries(case: ClinicalCase) -> list[str]:
    text = f"{case.case_id}\n{case.text}".lower()
    candidates = [
        ("essential thrombocythemia", "essential thrombocythemia AND extramedullary hematopoiesis"),
        ("extramedullary hematopoiesis", "extramedullary hematopoiesis AND lymph node"),
        ("jak2", "JAK2 AND essential thrombocythemia"),
        ("megakaryocyte", "megakaryocytic extramedullary hematopoiesis"),
        ("gallbladder", "gallbladder AND extramedullary hematopoiesis"),
        ("lymph node", "lymph node AND extramedullary hematopoiesis"),
        ("myeloproliferative", "myeloproliferative neoplasm AND extramedullary hematopoiesis"),
        ("cholecystitis", "cholecystitis AND lymph node pathology"),
    ]

    queries: list[str] = []
    for trigger, query in candidates:
        if trigger in text and query not in queries:
            queries.append(query)

    if queries:
        return queries[:6]

    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{4,}", case.text)
    stop_words = {
        "patient",
        "history",
        "diagnosis",
        "diagnostics",
        "management",
        "outcome",
        "presented",
        "revealed",
        "showed",
        "performed",
        "reported",
    }
    terms: list[str] = []
    for word in words:
        lower = word.lower()
        if lower in stop_words or lower in terms:
            continue
        terms.append(lower)
        if len(terms) >= 5:
            break
    return [" AND ".join(terms[:3])] if len(terms) >= 3 else []


def _extract_dois(text: str) -> list[str]:
    dois: list[str] = []
    for match in re.finditer(r"DOI:\s*([^|\n]+)", text):
        doi = match.group(1).strip().rstrip(".")
        if not doi or doi.lower() == "no doi":
            continue
        if doi not in dois:
            dois.append(doi)
    return dois
