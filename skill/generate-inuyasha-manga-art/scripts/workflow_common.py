#!/usr/bin/env python3
"""Shared, dependency-light helpers for the local Inuyasha art workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "references" / "source-library.json"
LEGACY_ALIASES_PATH = SKILL_DIR / "references" / "legacy-item-aliases.json"
DEFAULT_WORKFLOW_ROOT = Path(
    "/Users/jquery/Documents/inuYasha-design/reference-workflow"
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
FORM_VALUES = (
    "default-form",
    "human-form",
    "half-demon-form",
    "full-demon-form",
    "child-form",
    "tiny-form",
    "giant-form",
    "not-applicable",
)
FORM_TOKEN_MAP = {
    "默认形态": "default-form",
    "人类形态": "human-form",
    "半妖形态": "half-demon-form",
    "半妖": "half-demon-form",
    "半全妖形态": "full-demon-form",
    "全妖形态": "full-demon-form",
    "幼年形态": "child-form",
    "幼年": "child-form",
    "小形态": "tiny-form",
    "巨大形态": "giant-form",
    "不适用": "not-applicable",
}
SHOT_VALUES = (
    "full-body",
    "upper-body",
    "face",
    "profile",
    "back-view",
    "close-up",
    "medium-shot",
    "wide-shot",
    "two-shot",
    "group-shot",
    "action",
    "detail",
)
SHOT_TOKEN_MAP = {
    "全身": "full-body",
    "上身": "upper-body",
    "头部": "face",
    "表情": "face",
    "侧脸": "profile",
    "侧身": "profile",
    "背影": "back-view",
    "背面": "back-view",
    "特写": "close-up",
    "近景": "close-up",
    "中景": "medium-shot",
    "远景": "wide-shot",
    "双人": "two-shot",
    "群像": "group-shot",
    "动作": "action",
    "细节": "detail",
}
ANNOTATION_SHOT_MAP = {
    "suitable-for:close-up": "close-up",
    "suitable-for:two-shot": "two-shot",
    "suitable-for:full-body": "full-body",
    "suitable-for:back-view": "back-view",
    "suitable-for:establishing": "wide-shot",
    "view-angle:back": "back-view",
}
KNOWN_SUBJECTS = (
    "犬夜叉",
    "戈薇",
    "桔梗",
    "杀生丸",
    "弥勒",
    "珊瑚",
    "七宝",
    "云母",
    "邪见",
    "玲",
    "琥珀",
    "钢牙",
    "神乐",
    "神无",
    "十六夜",
    "枫婆婆",
    "幼年枫",
    "刀刀斋",
    "哞哞",
    "戈薇爷爷",
    "草太",
    "冥加",
    "铁碎牙",
    "天生牙",
    "食骨之井",
    "普通人物",
    "和尚",
    "场景",
)
CHARACTER_SUBJECTS = frozenset(
    subject
    for subject in KNOWN_SUBJECTS
    if subject not in {"铁碎牙", "天生牙", "食骨之井", "普通人物", "和尚", "场景"}
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_json(path)
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported source-library schema in {path}")
    return config


def workflow_root(config: dict[str, Any], override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    configured = config.get("workflow_root")
    return (
        Path(configured).expanduser().resolve() if configured else DEFAULT_WORKFLOW_ROOT
    )


def workflow_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "database": root / "catalog.sqlite3",
        "summary": root / "inventory-summary.json",
        "annotations": root / "annotations.jsonl",
        "tasks": root / "tasks",
        "browse": root / "browse",
        "contact_sheets": root / "contact-sheets",
        "rendered": root / "rendered",
    }


def ensure_workflow_dirs(root: Path) -> dict[str, Path]:
    paths = workflow_paths(root)
    for key in ("root", "tasks", "browse", "contact_sheets", "rendered"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def visible_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    return (
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


def library_signature(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    signature: dict[str, dict[str, Any]] = {}
    for source in config["sources"]:
        root = Path(source["path"])
        count = 0
        total_size = 0
        latest_mtime_ns = 0
        inventory_digest = hashlib.sha256()
        if root.is_dir():
            for path in sorted(
                visible_files(root), key=lambda item: str(item).casefold()
            ):
                extension = path.suffix.lower()
                if (
                    source["source_type"] == "image-directory"
                    and extension not in IMAGE_EXTENSIONS
                ):
                    continue
                stat = path.stat()
                relative = str(path.relative_to(root))
                count += 1
                total_size += stat.st_size
                latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
                inventory_digest.update(relative.encode("utf-8"))
                inventory_digest.update(b"\0")
                inventory_digest.update(str(stat.st_size).encode("ascii"))
                inventory_digest.update(b"\0")
                inventory_digest.update(str(stat.st_mtime_ns).encode("ascii"))
                inventory_digest.update(b"\n")
        signature[source["id"]] = {
            "exists": root.is_dir(),
            "file_count": count,
            "total_size": total_size,
            "latest_mtime_ns": latest_mtime_ns,
            "inventory_hash": inventory_digest.hexdigest(),
        }
    return signature


def source_config_fingerprint(config: dict[str, Any]) -> str:
    serialized = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str, fallback: str = "art-task") -> str:
    value = value.strip().lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or fallback


def find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    runtime = (
        Path(
            "/Users/jquery/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override"
        )
        / name
    )
    return str(runtime) if runtime.is_file() and os.access(runtime, os.X_OK) else None


def stable_file_item_id(source_id: str, content_hash: str) -> str:
    """Return an image id that survives renames and folder moves."""
    return f"{source_id}:file:{content_hash[:20]}"


def legacy_file_item_id(source_id: str, relative_path: str) -> str:
    """Return the schema-v1 path id so old annotations can be migrated."""
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"{source_id}:file:{digest}"


def folder_metadata(path: Path) -> tuple[str, str, list[str]]:
    """Return folder path, leaf content label, and inherited folder tags."""
    parts = [part.strip() for part in path.parent.parts if part not in ("", ".")]
    folder_path = "/".join(parts)
    content_label = parts[-1] if parts else ""
    return folder_path, content_label, parts


def infer_subjects(searchable: str) -> set[str]:
    """Match canonical subjects without leaking shorter names from longer ones."""
    matches = []
    for subject in KNOWN_SUBJECTS:
        start = 0
        while (index := searchable.find(subject, start)) >= 0:
            matches.append((index, index + len(subject), subject))
            start = index + len(subject)

    accepted: list[tuple[int, int, str]] = []
    for match in sorted(matches, key=lambda value: (-len(value[2]), value[0])):
        start, end, _ = match
        if any(start >= left and end <= right for left, right, _ in accepted):
            continue
        accepted.append(match)
    return {subject for _, _, subject in accepted}


def infer_subject_sequence(searchable: str) -> list[str]:
    """Return canonical subjects in textual order without shorter-name leakage."""
    matches = []
    for subject in KNOWN_SUBJECTS:
        start = 0
        while (index := searchable.find(subject, start)) >= 0:
            matches.append((index, index + len(subject), subject))
            start = index + len(subject)

    accepted: list[tuple[int, int, str]] = []
    for match in sorted(matches, key=lambda value: (-len(value[2]), value[0])):
        start, end, _ = match
        if any(start >= left and end <= right for left, right, _ in accepted):
            continue
        accepted.append(match)
    return [
        subject
        for _, _, subject in sorted(accepted, key=lambda value: (value[0], value[1]))
    ]


def apply_subject_form_aliases(
    subject: str, forms: set[str], source: dict[str, Any]
) -> set[str]:
    resolved = set(forms)
    aliases = source.get("subject_form_aliases", {}).get(subject, {})
    for source_form, compatible_forms in aliases.items():
        if source_form in resolved:
            resolved.update(compatible_forms)
    return resolved


def infer_subject_forms(
    path: Path,
    source: dict[str, Any],
    subjects: set[str],
    detected_forms: set[str],
    folder_tags: list[str],
) -> dict[str, list[str]]:
    """Pair each indexed character with its own compatible forms.

    Structured filenames may use `subject-subject__form-form__...`. When a
    multi-character filename supplies one non-default form, it applies to the
    first named subject and the remaining characters keep their configured
    default. Exact path overrides remain available for genuinely ambiguous art.
    """
    relative = path.as_posix()
    override = source.get("path_subject_form_overrides", {}).get(relative)
    if override is not None:
        return {
            subject: sorted(
                apply_subject_form_aliases(subject, set(forms), source),
                key=str.casefold,
            )
            for subject, forms in override.items()
            if subject in subjects
        }

    filename_parts = [part.strip() for part in re.split(r"__+", path.stem)]
    subject_sequence = infer_subject_sequence(filename_parts[0] if filename_parts else "")
    subject_sequence = [subject for subject in subject_sequence if subject in subjects]
    form_tokens = []
    if len(filename_parts) > 1:
        form_tokens = [
            FORM_TOKEN_MAP[token.strip()]
            for token in filename_parts[1].split("-")
            if token.strip() in FORM_TOKEN_MAP
        ]

    assignments: dict[str, set[str]] = {}
    if subject_sequence and len(form_tokens) == len(subject_sequence):
        assignments.update(
            {subject: {form} for subject, form in zip(subject_sequence, form_tokens)}
        )
    elif subject_sequence and len(form_tokens) == 1:
        if form_tokens[0] == "default-form":
            assignments.update(
                {subject: {"default-form"} for subject in subject_sequence}
            )
        else:
            assignments[subject_sequence[0]] = {form_tokens[0]}

    folder_defaults = source.get("folder_form_defaults", {})
    subject_defaults = source.get("subject_form_defaults", {})
    for subject in sorted(subjects, key=str.casefold):
        forms = assignments.get(subject)
        if forms is None and len(subjects) == 1 and detected_forms:
            forms = set(detected_forms)
        if forms is None:
            forms = set(subject_defaults.get(subject, []))
        if not forms:
            for folder in folder_tags:
                forms.update(folder_defaults.get(folder, []))
        if not forms and subject in CHARACTER_SUBJECTS:
            forms = {"default-form"}
        assignments[subject] = apply_subject_form_aliases(subject, forms, source)

    return {
        subject: sorted(forms, key=str.casefold)
        for subject, forms in sorted(assignments.items(), key=lambda item: item[0].casefold())
    }


def annotation_shot_types(tags: Iterable[str]) -> set[str]:
    return {ANNOTATION_SHOT_MAP[tag] for tag in tags if tag in ANNOTATION_SHOT_MAP}


def infer_structured_metadata(
    path: Path, source: dict[str, Any]
) -> dict[str, Any]:
    """Extract stable retrieval facets from folders and a lightweight filename grammar."""
    _, _, folder_tags = folder_metadata(path)
    searchable = " ".join([*folder_tags, path.stem])
    subjects = infer_subjects(searchable)

    forms = {value for token, value in FORM_TOKEN_MAP.items() if token in searchable}
    relative = path.as_posix()
    overrides = source.get("path_form_overrides", {})
    if relative in overrides:
        forms = set(overrides[relative])
    elif not forms:
        defaults = source.get("folder_form_defaults", {})
        for folder in folder_tags:
            forms.update(defaults.get(folder, []))

    subject_forms = infer_subject_forms(path, source, subjects, forms, folder_tags)
    paired_forms = {
        form for compatible_forms in subject_forms.values() for form in compatible_forms
    }
    if paired_forms:
        forms = paired_forms

    shot_types = {
        value for token, value in SHOT_TOKEN_MAP.items() if token in searchable
    }
    character_count = len(subjects & CHARACTER_SUBJECTS)
    if character_count == 2:
        shot_types.add("two-shot")
    elif character_count > 2:
        shot_types.add("group-shot")

    filename_terms = [
        part.strip() for part in re.split(r"__+", path.stem) if part.strip()
    ]
    return {
        "subjects": sorted(subjects),
        "forms": sorted(forms),
        "subject_forms": subject_forms,
        "shot_types": sorted(shot_types),
        "filename_terms": filename_terms,
    }


def infer_tags(path: Path, source: dict[str, Any]) -> list[str]:
    folder_path, content_label, folder_tags = folder_metadata(path)
    searchable = " ".join([folder_path, content_label, *folder_tags, path.stem])
    tags = set(source.get("default_tags", []))
    semantic = {
        "全身": "full-body",
        "上身": "upper-body",
        "头部": "face",
        "表情": "expression",
        "动作": "action",
        "细节": "detail",
        "对比": "scale-comparison",
        "武器": "weapon",
        "弓箭": "bow-arrow",
        "铁碎牙": "tessaiga",
        "锡杖": "staff",
        "飞来骨": "hiraikotsu",
        "风穴": "wind-tunnel",
        "人类形态": "human-form",
        "半妖": "half-demon-form",
        "全妖": "full-demon-form",
        "战斗": "combat",
        "飞行": "flying",
        "伤痕": "scar",
        "校服": "school-uniform",
        "巫女服": "priestess-clothing",
        "战斗服": "battle-outfit",
        "日常服": "casual-outfit",
        "和服": "kimono",
    }
    for token, tag in semantic.items():
        if token in searchable:
            tags.add(tag)
    for part in [*folder_tags, path.stem]:
        cleaned = part.replace("设定集", "").strip()
        if cleaned and not cleaned.startswith("."):
            tags.add(cleaned)
    structured = infer_structured_metadata(path, source)
    for field, values in structured.items():
        if field == "subject_forms":
            for subject, forms in values.items():
                tags.add(subject)
                tags.update(forms)
            continue
        tags.update(values)
    return sorted(tags)


def load_annotations(path: Path) -> dict[str, dict[str, Any]]:
    annotations: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return annotations
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
        item_id = row.get("item_id")
        if not item_id:
            raise ValueError(f"Missing item_id at {path}:{line_number}")
        current = annotations.setdefault(item_id, {"tags": [], "note": ""})
        current["tags"] = sorted(set(current["tags"]) | set(row.get("tags", [])))
        if row.get("note"):
            current["note"] = row["note"]
    return annotations


def open_database(path: Path, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection
