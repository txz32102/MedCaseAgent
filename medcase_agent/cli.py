from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .data import load_case
from .pipeline import MedCaseAgent
from .skills import SkillLibrary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MedCaseAgent pipeline.")
    parser.add_argument("case_path", type=Path, help="Case JSON, text file, or folder.")
    parser.add_argument("--env", type=Path, default=None, help="Path to .env file.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Run output folder.")
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=None,
        help="Folder containing */SKILL.md files.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Load the case and skills without calling the model.",
    )
    args = parser.parse_args(argv)

    settings = Settings.load(
        env_file=args.env,
        output_dir=args.output_dir,
        require_key=not args.validate_only,
    )

    if args.validate_only:
        case = load_case(args.case_path)
        skills = SkillLibrary(args.skills_dir or Path(__file__).resolve().parents[1] / "skills")
        print(f"case_id={case.case_id}")
        print(f"images={len(case.images)}")
        print(f"skills={', '.join(skills.names())}")
        return 0

    final_path = MedCaseAgent(settings, skill_dir=args.skills_dir).run_case(args.case_path)
    print(f"final={final_path}")
    return 0
