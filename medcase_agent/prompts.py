from __future__ import annotations

import json

from .models import ClinicalCase


BASE_INSTRUCTIONS = """You are MedCaseAgent, a clinical case-report drafting agent.
Work as a careful medical writer, not as a treating clinician. Preserve source facts,
avoid unsupported diagnosis or management claims, and require human clinical review.
Use the active skills as operating procedures. Do not mention the skills in outputs."""


def instructions(stage: str, skills: str) -> str:
    return f"{BASE_INSTRUCTIONS}\n\n# Stage\n{stage}\n\n# Active Skills\n{skills}"


def planner_prompt(case: ClinicalCase, citation_bank: str = "") -> str:
    return f"""{case_context(case, citation_bank)}

Create a concise manuscript plan.

Return Markdown with exactly these headings:
# Plan
## Case Thesis
## Source Facts To Preserve
## Section Blueprint
## Figure Plan
## Citation Plan
## Risk Checks"""


def writer_prompt(case: ClinicalCase, plan: str, citation_bank: str = "") -> str:
    return f"""{case_context(case, citation_bank)}

# Approved Plan
{plan}

Draft the manuscript in Markdown. Write the clinical article only. Keep section
headings useful and conventional for a case report. Use verified citation-bank
entries when supplied, and do not write that references are unavailable if a
verified citation bank is present. Use image links exactly as shown in the image
index when figures are relevant."""


def refiner_prompt(case: ClinicalCase, plan: str, draft: str, citation_bank: str = "") -> str:
    return f"""{case_context(case, citation_bank)}

# Approved Plan
{plan}

# Draft To Refine
{draft}

Refine the draft into the final Markdown manuscript. Preserve factual alignment
with the source case, remove unsupported statements, repair figure placement, and
use verified citation-bank entries when supplied. Do not write that references
are unavailable if a verified citation bank is present. Output only the final
manuscript."""


def case_context(case: ClinicalCase, citation_bank: str = "") -> str:
    metadata = json.dumps(case.metadata, ensure_ascii=False, indent=2)
    citation_section = ""
    if citation_bank.strip():
        citation_section = f"""

## Verified Citation Bank
{citation_bank.strip()}"""
    return f"""# Case Context
Case ID: {case.case_id}
Source: {case.source_path}

## Metadata
```json
{metadata}
```

## Clinical Record
{case.text}

## Image Index
{case.image_index()}{citation_section}"""
