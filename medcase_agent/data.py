from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .models import ClinicalCase, ImageAsset

IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
IMAGE_SUBDIRS = ("imgs", "images", "figures")
TEXT_EXTS = {".md", ".txt", ".text", ".xml"}
PREFERRED_JSON = ("case.json", "clinical_data.json", "record.json", "atoms.json")
CASE_SECTION_ORDER = (
    "title",
    "abstract",
    "history",
    "presentation",
    "diagnosis",
    "diagnostics",
    "management",
    "outcome",
    "timeline",
    "figures",
    "references",
    "clinical_data",
    "text",
)


def load_case(path: Path, char_limit: int = 120000) -> ClinicalCase:
    path = path.expanduser().resolve()
    if path.is_file():
        return _load_file_case(path, char_limit)
    if path.is_dir():
        return _load_dir_case(path, char_limit)
    raise FileNotFoundError(path)


def _load_dir_case(path: Path, char_limit: int) -> ClinicalCase:
    json_path = _find_json(path)
    if json_path:
        base = _load_file_case(json_path, char_limit)
        return ClinicalCase(
            case_id=base.case_id or path.name,
            source_path=path,
            text=base.text,
            metadata=base.metadata,
            images=_images(path),
        )

    chunks = []
    for text_file in sorted(path.iterdir()):
        if text_file.suffix.lower() not in TEXT_EXTS:
            continue
        if text_file.name.lower() in {"readme.md"}:
            continue
        chunks.append(f"# Source file: {text_file.name}\n\n{_read_text_file(text_file)}")

    if not chunks:
        raise ValueError(f"No case JSON, Markdown, text, or XML files found in {path}")

    return ClinicalCase(
        case_id=path.name,
        source_path=path,
        text=_limit("\n\n".join(chunks), char_limit),
        metadata={},
        images=_images(path),
    )


def _load_file_case(path: Path, char_limit: int) -> ClinicalCase:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
        return ClinicalCase(
            case_id=_case_id(path, data),
            source_path=path,
            text=_limit(_json_to_text(data), char_limit),
            metadata=metadata if isinstance(metadata, dict) else {},
            images=_images(path.parent),
        )

    return ClinicalCase(
        case_id=path.stem,
        source_path=path,
        text=_limit(_read_text_file(path), char_limit),
        metadata={},
        images=_images(path.parent),
    )


def _find_json(path: Path) -> Path | None:
    for name in PREFERRED_JSON:
        candidate = path / name
        if candidate.exists():
            return candidate
    atoms = sorted(path.glob("*_atoms.json"))
    if atoms:
        return atoms[0]
    json_files = sorted(p for p in path.glob("*.json") if p.name != "metadata.json")
    return json_files[0] if json_files else None


def _images(path: Path) -> list[ImageAsset]:
    images = []
    for image_path in _image_paths(path):
        mime = IMAGE_MIME.get(image_path.suffix.lower())
        if not mime:
            continue
        ref = f"IMG_{len(images) + 1:03d}"
        images.append(ImageAsset(ref, image_path, mime, image_path.name))
    return images


def _image_paths(path: Path) -> list[Path]:
    candidates: list[Path] = []
    search_dirs = [path]
    search_dirs.extend(path / name for name in IMAGE_SUBDIRS)

    seen: set[Path] = set()
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for candidate in sorted(search_dir.iterdir()):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(candidate)
    return candidates


def _read_text_file(path: Path) -> str:
    if path.suffix.lower() == ".xml":
        try:
            root = ET.parse(path).getroot()
            text = " ".join(part.strip() for part in root.itertext() if part.strip())
            return re.sub(r"\s+", " ", text)
        except Exception:
            pass
    return path.read_text(encoding="utf-8", errors="replace")


def _json_to_text(data: Any) -> str:
    if not isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False, indent=2)

    lines = []
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        for key in ("title", "abstract", "journal", "pub_date", "pmid", "pmc_id"):
            if metadata.get(key):
                lines.append(f"{key}: {metadata[key]}")

    seen = {"metadata"}
    for key in CASE_SECTION_ORDER:
        if key in data:
            seen.add(key)
            lines.append(_format_section(key, data[key]))
    for key in sorted(k for k in data if k not in seen):
        lines.append(_format_section(key, data[key]))
    return "\n\n".join(part for part in lines if part.strip())


def _format_section(name: str, value: Any) -> str:
    title = name.replace("_", " ").title()
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        body = "\n".join(f"- {_compact(item)}" for item in value)
    elif isinstance(value, dict):
        body = "\n".join(f"- {key}: {_compact(val)}" for key, val in value.items())
    else:
        body = str(value).strip()
    return f"## {title}\n{body}"


def _compact(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return re.sub(r"\s+", " ", str(value)).strip()


def _case_id(path: Path, data: Any) -> str:
    if isinstance(data, dict):
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        for key in ("folder_id", "case_id", "pmid", "pmc_id", "id"):
            value = metadata.get(key) or data.get(key)
            if value:
                return _slug(str(value))
    if path.name in PREFERRED_JSON and path.parent.name:
        return _slug(path.parent.name)
    return _slug(path.stem.replace("_atoms", ""))


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def _limit(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[Truncated by case loader]"
