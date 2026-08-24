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
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "references" / "source-library.json"
LEGACY_ALIASES_PATH = SKILL_DIR / "references" / "legacy-item-aliases.json"
WORKFLOW_HOME_ENV = "INUYASHA_WORKFLOW_HOME"
WORKFLOW_ROOT_ENV = "INUYASHA_WORKFLOW_ROOT"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
FORM_VALUES = (
    "default-form",
    "human-form",
    "half-demon-form",
    "half-demon-unrobed-form",
    "full-demon-form",
    "child-form",
    "tiny-form",
    "giant-form",
    "demon-slayer-form",
    "battle-armor-form",
    "untransformed-form",
    "transformed-form",
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
    "退治屋服形态": "demon-slayer-form",
    "退治屋服": "demon-slayer-form",
    "战斗服形态": "battle-armor-form",
    "战斗服": "battle-armor-form",
    "未变化形态": "untransformed-form",
    "变化前形态": "untransformed-form",
    "变化后形态": "transformed-form",
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
VIEW_ANGLE_VALUES = (
    "front",
    "three-quarter-front",
    "profile",
    "three-quarter-back",
    "back",
    "high-angle",
    "low-angle",
    "multi-view",
)
VIEW_ANGLE_SHOT_MAP = {
    "profile": "profile",
    "back": "back-view",
}
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
    "言灵念珠",
    "飞来骨",
    "锡杖",
    "人头杖",
    "神无圆镜",
    "神乐折扇",
    "十六夜墓碑",
    "食骨之井",
    "普通人物",
    "和尚",
    "场景",
)
CHARACTER_SUBJECTS = frozenset(
    subject
    for subject in KNOWN_SUBJECTS
    if subject
    not in {
        "铁碎牙",
        "天生牙",
        "言灵念珠",
        "飞来骨",
        "锡杖",
        "人头杖",
        "神无圆镜",
        "神乐折扇",
        "十六夜墓碑",
        "食骨之井",
        "场景",
    }
)
OFFICIAL_IDENTITY_FACETS = (
    "face",
    "hair-ear",
    "costume",
    "garment-overlap",
    "hands",
    "feet",
    "prop-attachment",
    "construction",
)
NON_HUMANOID_SUBJECTS = frozenset({"云母", "哞哞"})
OFFICIAL_PROP_SUBJECTS = frozenset(
    {"人头杖", "神乐折扇", "神无圆镜", "言灵念珠", "铁碎牙", "锡杖", "飞来骨"}
)
REFERENCE_DOMAINS = (
    "identity",
    "character-style",
    "scene",
    "continuity",
    "legacy-unrouted",
)
SCENE_TRAIT_PREFIXES = (
    "scene-",
    "detail-falloff:",
    "background:",
    "effect-type:",
    "content-object:",
)
SCENE_ECONOMY_CUE_PREFIXES = (
    "scene-id:",
    "background:",
    "effect-type:",
    "content-object:",
)


def identity_facet_tag(subject: str, form: str, facet: str) -> str:
    if form not in FORM_VALUES:
        raise ValueError(f"unsupported identity form: {form}")
    if facet not in OFFICIAL_IDENTITY_FACETS:
        raise ValueError(f"unsupported official identity facet: {facet}")
    return f"identity-facet:{subject}:{form}:{facet}"


def parse_identity_facet_tag(tag: str) -> tuple[str, str, str] | None:
    parts = tag.split(":", 3)
    if (
        len(parts) != 4
        or parts[0] != "identity-facet"
        or parts[2] not in FORM_VALUES
        or parts[3] not in OFFICIAL_IDENTITY_FACETS
    ):
        return None
    return parts[1], parts[2], parts[3]


def _json_record_value(item: Any, field: str, default: Any) -> Any:
    try:
        value = item[field]
    except (KeyError, IndexError, TypeError):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def item_identity_facets(item: Any, subject: str, form: str) -> set[str]:
    facets = set()
    tags = set(_json_record_value(item, "tags", []))
    for tag in tags:
        parsed = parse_identity_facet_tag(str(tag))
        if parsed and parsed[:2] == (subject, form):
            facets.add(parsed[2])
    subject_forms = _json_record_value(item, "subject_forms", {})
    if subject_forms.get(subject) != [form]:
        return facets
    shots = set(_json_record_value(item, "shot_types", []))
    exact_subjects = {
        name for name, forms in subject_forms.items() if len(forms) == 1
    }
    exact_characters = exact_subjects & set(CHARACTER_SUBJECTS)
    exact_props = exact_subjects & set(OFFICIAL_PROP_SUBJECTS)
    if subject in exact_characters and len(exact_characters) == 1:
        if "face" in shots or (
            subject in NON_HUMANOID_SUBJECTS and "full-body" in shots
        ):
            facets.update({"face", "hair-ear"})
        if subject not in NON_HUMANOID_SUBJECTS:
            if shots & {"full-body", "upper-body"}:
                facets.add("costume")
            if shots & {"full-body", "upper-body", "action"}:
                facets.add("hands")
            if (
                "suitable-for:garment-overlap" in tags
                or "occlusion:garment-prop" in tags
            ):
                facets.add("garment-overlap")
            if len(exact_props) == 1 and any(
                tag.startswith("prop-attachment:") for tag in tags
            ):
                facets.add("prop-attachment")
        if "full-body" in shots or "suitable-for:footwear" in tags:
            facets.add("feet")
    if subject in exact_props and len(exact_props) == 1:
        if any(tag.startswith("prop-attachment:") for tag in tags):
            facets.add("prop-attachment")
        try:
            relative_path = str(item["relative_path"])
        except (KeyError, IndexError, TypeError):
            relative_path = ""
        if "suitable-for:weapon-construction" in tags or (
            "detail" in shots and subject in relative_path
        ):
            facets.add("construction")
    return facets


def cropped_identity_item(item: Any, declared_tags: Iterable[str]) -> dict[str, Any]:
    """Restrict a cropped official page to explicitly declared visible facets."""
    tags = list(dict.fromkeys(str(tag) for tag in declared_tags))
    if not tags:
        raise ValueError("cropped identity reference requires identity_facets")
    for tag in tags:
        parsed = parse_identity_facet_tag(tag)
        if parsed is None:
            raise ValueError(f"invalid cropped identity facet: {tag}")
        subject, form, facet = parsed
        if facet not in item_identity_facets(item, subject, form):
            raise ValueError(
                "cropped identity facet is not provided by the source page: "
                f"{subject}={form}:{facet}"
            )
    restricted = dict(item)
    restricted["shot_types"] = []
    restricted["tags"] = tags
    return restricted


def official_facet_coverage(
    items: Iterable[Any], subject: str, form: str, required: Iterable[str]
) -> dict[str, Any]:
    required_facets = list(dict.fromkeys(required))
    unknown = sorted(set(required_facets) - set(OFFICIAL_IDENTITY_FACETS))
    if unknown:
        raise ValueError(f"unsupported official identity facets: {unknown}")
    exact_items = []
    providers = {facet: [] for facet in required_facets}
    for item in items:
        roles = set(_json_record_value(item, "eligible_roles", ["identity"]))
        subject_forms = _json_record_value(item, "subject_forms", {})
        if "identity" not in roles or form not in subject_forms.get(subject, []):
            continue
        item_id = str(item["item_id"])
        exact_items.append(item_id)
        for facet in item_identity_facets(item, subject, form):
            if facet in providers:
                providers[facet].append(item_id)
    missing = [facet for facet in required_facets if not providers[facet]]
    status = "MISS" if not exact_items else "INSUFFICIENT" if missing else "HIT"
    return {
        "subject": subject,
        "form": form,
        "status": status,
        "required_facets": required_facets,
        "missing_facets": missing,
        "providers": providers,
        "eligible_item_ids": exact_items,
    }


def required_official_facets(
    identity_forms: dict[str, str],
    prop_forms: dict[str, str],
    shot: str | None,
) -> list[dict[str, Any]]:
    requirements = []
    needs_hands = shot not in {None, "face", "close-up", "profile"}
    needs_feet = shot in {"full-body", "wide-shot", "action"}
    for subject, form in identity_forms.items():
        facets = ["face", "hair-ear"]
        if subject not in NON_HUMANOID_SUBJECTS:
            facets.append("costume")
            if needs_hands:
                facets.append("hands")
        if needs_feet:
            facets.append("feet")
        requirements.append({"subject": subject, "form": form, "required": facets})
    for subject, form in prop_forms.items():
        requirements.append(
            {
                "subject": subject,
                "form": form,
                "required": ["construction", "prop-attachment"],
            }
        )
    return requirements


def eligible_character_style_candidate(
    item: dict[str, Any], requested_subject_forms: Iterable[tuple[str, str]]
) -> bool:
    """Return whether a style candidate depicts only requested exact forms.

    Character and form are hard eligibility constraints for character-style
    rendering. Ranking may order the eligible set by view, shot, or feedback,
    but an unrequested known character or a wrong requested form is never a
    candidate. Canonical props and other non-character subjects are unaffected.
    """
    requested_pairs = list(requested_subject_forms)
    item_forms = {
        str(subject).casefold(): {str(value).casefold() for value in forms}
        for subject, forms in item.get("subject_forms", {}).items()
    }
    requested_subjects = {subject.casefold() for subject, _ in requested_pairs}
    requested_forms_by_subject: dict[str, set[str]] = {}
    for subject, form in requested_pairs:
        requested_forms_by_subject.setdefault(subject.casefold(), set()).add(
            form.casefold()
        )
    known_character_subjects = {subject.casefold() for subject in CHARACTER_SUBJECTS}
    depicted_subjects = item.get("subjects") or item_forms.keys()
    item_character_subjects = {
        str(subject).casefold() for subject in depicted_subjects
    }.intersection(known_character_subjects)
    return (
        bool(item_character_subjects)
        and item_character_subjects.issubset(requested_subjects)
        and all(
            bool(
                item_forms.get(subject, set()).intersection(
                    requested_forms_by_subject[subject]
                )
            )
            for subject in item_character_subjects
        )
    )


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def is_repository_root(candidate: Path) -> bool:
    return (
        (candidate / "workflow" / "reference-workflow").is_dir()
        and (candidate / "libraries").is_dir()
        and (candidate / "skill" / SKILL_DIR.name).is_dir()
    )


def repository_root() -> Path:
    """Return the portable repository root used by bundled libraries.

    A repo-local checkout always owns its bundled workflow data. A copied
    user-level skill cannot infer the clone location, so the Windows setup script
    persists ``INUYASHA_WORKFLOW_HOME`` for that installed-copy case.
    """
    candidate = SKILL_DIR.parent.parent
    if is_repository_root(candidate):
        return candidate.resolve()
    configured = os.environ.get(WORKFLOW_HOME_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if is_repository_root(candidate):
            return candidate.resolve()
    return SKILL_DIR.parent.parent.resolve()


def expand_config_path(value: str | Path) -> Path:
    """Expand workflow tokens and environment variables into an absolute path."""
    text = str(value)
    replacements = {
        "${REPO_ROOT}": str(repository_root()),
        "${SKILL_DIR}": str(SKILL_DIR),
        "${HOME}": str(Path.home()),
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    expanded = Path(os.path.expandvars(text)).expanduser()
    if not expanded.is_absolute():
        expanded = repository_root() / expanded
    return expanded.resolve()


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(
                    f"Duplicate JSON key in source-library config: {key}"
                )
            result[key] = value
        return result

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle, object_pairs_hook=reject_duplicate_keys)
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported source-library schema in {path}")
    if config.get("workflow_root"):
        config["workflow_root"] = str(expand_config_path(config["workflow_root"]))
    for source in config.get("sources", []):
        source["path"] = str(expand_config_path(source["path"]))
        candidate_series_index(source)
    for alias in config.get("path_aliases", []):
        alias["to"] = str(expand_config_path(alias["to"]))
    return config


def candidate_series_index(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return validated, path-keyed candidate-series metadata for one source."""
    raw_series = source.get("candidate_series", [])
    if not isinstance(raw_series, list):
        raise ValueError(
            f"{source.get('id', 'source')}.candidate_series must be a list"
        )
    if raw_series and source.get("id") != "official":
        raise ValueError("candidate_series may be declared only by the official source")

    index: dict[str, dict[str, Any]] = {}
    series_ids: set[str] = set()
    for raw in raw_series:
        if not isinstance(raw, dict):
            raise ValueError("candidate_series entries must be objects")
        series_id = raw.get("id")
        members = raw.get("members")
        default_member = raw.get("default_member")
        if not isinstance(series_id, str) or not series_id.strip():
            raise ValueError("candidate_series.id must be a non-empty string")
        if series_id in series_ids:
            raise ValueError(f"duplicate candidate series id: {series_id}")
        series_ids.add(series_id)
        if not isinstance(members, list) or len(members) < 2:
            raise ValueError(
                f"candidate series {series_id} must have at least two members"
            )

        member_paths: list[str] = []
        normalized_members: list[tuple[str, list[str]]] = []
        for member in members:
            if not isinstance(member, dict):
                raise ValueError(
                    f"candidate series {series_id} members must be objects"
                )
            member_path = member.get("path")
            selection_terms = member.get("selection_terms", [])
            if not isinstance(member_path, str) or not member_path.strip():
                raise ValueError(
                    f"candidate series {series_id} member.path must be non-empty"
                )
            member_path = member_path.replace("\\", "/")
            if member_path in index or member_path in member_paths:
                raise ValueError(f"duplicate candidate series member: {member_path}")
            if not isinstance(selection_terms, list) or not all(
                isinstance(term, str) and term.strip() for term in selection_terms
            ):
                raise ValueError(
                    f"candidate series {series_id} selection_terms must be strings"
                )
            member_paths.append(member_path)
            normalized_members.append((member_path, selection_terms))
        if default_member not in member_paths:
            raise ValueError(
                f"candidate series {series_id} default_member must name one member"
            )
        for member_path, selection_terms in normalized_members:
            index[member_path] = {
                "series_id": series_id,
                "series_size": len(member_paths),
                "default": member_path == default_member,
                "selection_terms": selection_terms,
            }
    return index


def workflow_root(config: dict[str, Any], override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    environment_root = os.environ.get(WORKFLOW_ROOT_ENV)
    if environment_root:
        return Path(environment_root).expanduser().resolve()
    configured = config.get("workflow_root")
    if configured:
        return Path(configured).expanduser().resolve()
    return (repository_root() / "workflow" / "reference-workflow").resolve()


def resolve_recorded_path(
    value: str | Path, config: dict[str, Any] | None = None
) -> Path:
    """Resolve a current or historical recorded path without rewriting records.

    Task and attempt JSON remains append-only. On a different machine, configured
    aliases translate the old absolute prefix to the repository snapshot.
    """
    normalized = str(value).replace("\\", "/").rstrip("/")
    active_config = config if config is not None else load_config()
    for alias in active_config.get("path_aliases", []):
        source = str(alias.get("from", "")).replace("\\", "/").rstrip("/")
        if not source or not (
            normalized == source or normalized.startswith(source + "/")
        ):
            continue
        suffix = normalized[len(source) :].lstrip("/")
        target = Path(alias["to"])
        if suffix:
            target = target.joinpath(*suffix.split("/"))
        return target.expanduser().resolve()
    candidate = Path(value).expanduser()
    if candidate.exists():
        return candidate.resolve()
    return candidate.resolve()


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


def visible_files(
    root: Path, exclude_globs: Iterable[str] = ()
) -> Iterable[Path]:
    if not root.is_dir():
        return []
    patterns = tuple(pattern.replace("\\", "/") for pattern in exclude_globs)
    return (
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
        and not any(
            fnmatchcase(path.relative_to(root).as_posix(), pattern)
            for pattern in patterns
        )
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
                visible_files(root, source.get("exclude_globs", [])),
                key=lambda item: str(item).casefold(),
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
    environment_name = f"INUYASHA_{name.upper().replace('-', '_')}"
    configured = os.environ.get(environment_name)
    if configured and Path(configured).expanduser().is_file():
        return str(Path(configured).expanduser().resolve())
    found = shutil.which(name)
    return found


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
    subject_sequence = infer_subject_sequence(
        filename_parts[0] if filename_parts else ""
    )
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

    # The filename form slot describes the character.  A Tessaiga state in the
    # content slot describes the weapon itself and must win over that form.
    filename_terms = set(filename_parts[2:])
    if "铁碎牙" in subjects:
        if "未变化铁碎牙" in filename_terms:
            assignments["铁碎牙"] = {"untransformed-form"}
        elif "变化铁碎牙" in filename_terms:
            assignments["铁碎牙"] = {"transformed-form"}

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
        for subject, forms in sorted(
            assignments.items(), key=lambda item: item[0].casefold()
        )
    }


def annotation_shot_types(tags: Iterable[str]) -> set[str]:
    return {ANNOTATION_SHOT_MAP[tag] for tag in tags if tag in ANNOTATION_SHOT_MAP}


def reference_domain_for(
    source_id: str,
    relative_paths: Iterable[str],
    subjects: Iterable[str] = (),
) -> str:
    """Assign one authority domain before any relevance scoring.

    A curated image copied into the top-level ``场景`` folder is deliberately
    scene evidence, even when a character is visible.  This prevents action or
    co-occurring-character similarity from leaking into character-style search.
    """
    if source_id == "official":
        return "identity"
    if source_id in {"selected-output", "user-continuity"}:
        return "continuity"
    if source_id in {"manga-curated", "tv-curated"}:
        for relative_path in relative_paths:
            parts = Path(relative_path).parts
            if parts and parts[0] == "场景":
                return "scene"
        if set(subjects).intersection(CHARACTER_SUBJECTS):
            return "character-style"
    return "legacy-unrouted"


def retrieval_traits_for_domain(
    traits: Iterable[str], reference_domain: str | None
) -> list[str]:
    """Keep only signals owned by a retrieval domain.

    Character style deliberately ignores action, interaction, expression and
    scene terms, but retains view angle because face/hair mark-making must be
    applicable to the requested view. Scene retrieval deliberately ignores
    character/action terms. Identity remains an exact-facet lookup and receives
    no intent-score terms.
    """
    unique = list(dict.fromkeys(traits))
    if reference_domain == "character-style":
        return [trait for trait in unique if trait.startswith("view-angle:")]
    if reference_domain == "scene":
        return [
            trait
            for trait in unique
            if trait.startswith(SCENE_TRAIT_PREFIXES)
        ]
    if reference_domain == "identity":
        return []
    return unique


CANONICAL_SCENE_RULES = (
    ("bone-eaters-well", "食骨之井", ("食骨之井", "食骨井")),
    ("goshinboku", "御神木", ("御神木", "时代树", "時代樹")),
)

NEGATED_ALIAS_PREFIX = re.compile(
    r"(?:不要|不能|不得|不可|不允许|不希望|不想要|不需要|不出现|不在|不画|"
    r"别画|别|无需|没有|不是|排除|去掉|禁止|严禁|避免|无|不|未|没)"
    r"(?:(?:[\s，,:：、]*"
    r"(?:让|希望|在|画面|场景|构图|背景|前景|中景|远景|中|内|里|远处|再|"
    r"有|画出?|出现|手持|持有|持|拿着?|拿|带着?|带|携带|佩戴|使用|握住|"
    r"任何|一个|一处|该|这个|的)"
    r"[\s，,:：、]*)*)$"
)


def has_nonnegated_alias(normalized: str, aliases: Iterable[str]) -> bool:
    alias_terms = tuple(alias.casefold() for alias in aliases)
    spans = {
        (match.start(), match.end())
        for alias in alias_terms
        for match in re.finditer(re.escape(alias), normalized)
    }
    widest_end = -1
    for start, end in sorted(spans, key=lambda span: (span[0], -span[1])):
        if end <= widest_end:
            continue
        widest_end = end
        prefix = normalized[max(0, start - 16) : start]
        cleaned_prefix = prefix
        for alias in alias_terms:
            cleaned_prefix = cleaned_prefix.replace(alias, "")
        if not prefix.endswith(("不", "未", "没")) and not NEGATED_ALIAS_PREFIX.search(
            cleaned_prefix
        ):
            return True
    return False


def infer_canonical_scene(text: str) -> dict[str, str] | None:
    normalized = " ".join(text.casefold().split())
    for scene_id, label, aliases in CANONICAL_SCENE_RULES:
        if has_nonnegated_alias(normalized, aliases):
            return {"id": scene_id, "label": label}
    return None


REFERENCE_ROLE_TAGS = {
    "reference-role:identity-only": {"identity"},
    "reference-role:rendering-only": {"rendering"},
    "reference-role:composition-only": {"composition"},
    "reference-role:content-only": {"content"},
    "reference-role:continuity-only": {"continuity"},
    "reference-role:target-only": {"target"},
    "reference-role:palette-only": {"palette"},
}


INTENT_TRAIT_RULES = (
    ("scene-id:bone-eaters-well", ("食骨之井", "食骨井")),
    ("scene-id:goshinboku", ("御神木", "时代树", "時代樹")),
    ("action:embrace-from-behind", ("背后拥抱", "从背后抱", "从身后抱")),
    ("action:embrace", ("拥抱", "相拥", "抱住对方")),
    ("action:carry", ("抱在怀里", "抱着孩子", "怀抱孩子", "抱起")),
    ("action:reach", ("伸手", "伸向", "伸出双手", "双臂伸出")),
    ("action:hold", ("手持", "握住", "托住", "抱球", "持刀", "扶住", "承托")),
    ("action:cut", ("切大根", "切萝卜", "切菜", "用刀切")),
    ("action:turn-head", ("回头", "转头")),
    ("action:look-up", ("抬头", "仰头", "看向天空", "看向天上")),
    (
        "action:sleeve-hidden-hands",
        ("藏在袖中", "袖中藏手", "双手藏袖", "藏进宽袖", "袖手", "揣手"),
    ),
    ("action:face-off", ("正面对峙", "迎面对峙")),
    ("action:draw-weapon", ("拔刀", "拔剑", "出鞘")),
    ("action:sheath-weapon", ("收刀", "收剑", "入鞘", "纳刀")),
    ("action:swing-weapon", ("挥刀", "挥剑", "挥动铁碎牙", "挥出铁碎牙")),
    ("action:activate-wind-tunnel", ("发动风穴", "开启风穴", "张开风穴")),
    ("action:ride", ("骑乘", "骑马", "骑着")),
    ("action:fly", ("飞行", "飞翔")),
    ("action:transform", ("变身", "变化过程", "由小变大")),
    ("action:conjure", ("施放狐火", "召出狐火", "召唤狐火")),
    ("action:fall", ("跌倒", "摔倒", "倒地")),
    ("action:jump", ("跳起", "跃起", "腾空")),
    ("action:run", ("奔跑", "跑向", "冲向")),
    ("action:sit", ("坐姿", "坐在", "并排坐", "相对而坐")),
    ("action:kneel", ("跪坐", "跪在", "屈膝")),
    ("action:crouch", ("蹲坐", "蹲下", "半蹲")),
    ("action:pass-ball", ("传球", "把球传给", "向前递球")),
    ("action:catch-ball", ("接球", "准备接球", "双手接球")),
    ("action:kick-ball", ("踢球", "传踢", "蹴鞠")),
    ("action:comb-hair", ("梳头", "梳理头发", "用梳子")),
    ("action:touch-ears", ("把玩犬耳", "揉弄犬耳", "捏犬耳", "摸犬耳")),
    ("action:adjust-clothing", ("整理衣领", "抚平衣领", "扶正衣领", "整理宽袖")),
    (
        "interaction:mother-child",
        (
            "母子",
            "母亲与孩子",
            "十六夜与幼年犬夜叉",
            "十六夜和幼年犬夜叉",
            "幼年犬夜叉与十六夜",
            "幼年犬夜叉和十六夜",
        ),
    ),
    ("interaction:romantic", ("恋人", "浪漫", "爱意", "恋慕")),
    ("interaction:face-to-face", ("面对面", "相对站立", "相对而坐")),
    (
        "interaction:body-contact",
        ("身体接触", "相依", "靠在", "倚靠", "抱在怀里", "拥抱"),
    ),
    ("interaction:hand-prop", ("手持", "握住", "托住", "抱球", "抓住刀柄", "用梳子")),
    (
        "interaction:hand-clothing",
        ("抓住衣领", "衣领", "整理衣领", "抚平衣领", "袖口"),
    ),
    ("interaction:shoulder-rest", ("靠在肩", "倚靠肩", "靠肩")),
    ("interaction:shared-gaze", ("对视", "四目相对", "目光交汇", "看向彼此")),
    ("interaction:confrontation", ("对峙", "揪住", "抓住衣领")),
    ("interaction:caregiving", ("照顾", "抚摸", "梳头", "整理衣领", "扶抱", "承托")),
    ("interaction:teaching", ("教他", "亲身示范", "礼仪教学", "示范给")),
    ("interaction:ear-touch", ("把玩犬耳", "揉弄犬耳", "捏犬耳", "摸犬耳")),
    ("interaction:rider-mount", ("骑乘关系", "骑在", "坐骑")),
    ("interaction:scale-reference", ("身高对比", "体型对比", "比例对比")),
    ("expression:alert-sad", ("清醒而忧伤", "清醒且悲伤", "睁眼忧伤", "倔强悲伤")),
    ("expression:shy", ("害羞", "羞涩")),
    ("expression:surprised", ("惊讶", "吃惊", "惊呼", "愕然")),
    ("expression:gentle", ("温柔", "柔和", "慈爱")),
    ("expression:restrained", ("克制", "隐忍", "压抑")),
    ("expression:angry", ("愤怒", "生气", "恼怒")),
    ("expression:determined", ("坚定", "决然", "专注")),
    ("expression:crying", ("哭泣", "泪水", "泪痕", "含泪", "落泪")),
    ("content-object:knife", ("菜刀", "短刀", "小刀")),
    ("content-object:daikon", ("大根", "萝卜")),
    ("content-object:grave", ("墓碑", "墓地", "坟墓", "墓前")),
    ("content-object:tessaiga", ("铁碎牙",)),
    ("content-object:tenseiga", ("天生牙",)),
    ("content-object:ball", ("玩球", "传球", "接球", "抱球", "球仍", "蹴鞠", "鹿革鞠")),
    ("content-object:shopping-bag", ("购物袋", "杂货袋", "采购袋")),
    ("content-object:bow", ("弓箭", "长弓", "持弓")),
    ("content-object:well", ("食骨之井", "井边", "井沿")),
    ("content-object:tree", ("御神木", "神木", "巨树")),
    ("content-object:comb", ("梳子", "木梳", "细齿梳")),
    ("content-object:mirror", ("梳妆镜", "铜镜", "镜中倒影", "镜面")),
    ("content-object:hair-ribbon", ("发绳", "束发结")),
    ("content-object:robe-sleeve", ("宽袖", "袖口", "衣袖", "袖中")),
    ("content-object:shrine", ("神社", "鸟居")),
    ("content-object:beads-of-subjugation", ("言灵念珠", "言靈念珠")),
    ("content-object:staff", ("锡杖", "錫杖")),
    ("content-object:prayer-beads", ("风穴念珠", "封印念珠")),
    ("content-object:wind-tunnel-seal", ("风穴封印", "封印缠布")),
    ("content-object:hiraikotsu", ("飞来骨", "飛来骨")),
    ("content-object:arrow", ("箭矢", "箭支")),
    ("content-object:quiver", ("箭筒", "箭袋")),
    ("content-object:backpack", ("双肩包", "背包", "书包")),
    ("content-object:medical-kit", ("医药箱", "急救箱")),
    ("content-object:sword", ("佩剑", "佩刀", "腰间刀")),
    ("content-object:staff-of-two-heads", ("人头杖",)),
    ("content-object:hammer", ("锤子", "铁锤")),
    ("content-object:harness", ("鞍具", "缰具", "缰绳")),
    ("content-object:fan", ("折扇", "扇子")),
    ("content-object:feather", ("羽毛",)),
    ("content-object:horse", ("马匹", "骑马")),
    ("content-object:mask", ("面具", "战斗面具")),
    ("content-object:travel-pack", ("背箱", "行囊")),
    ("content-object:walking-stick", ("手杖", "拐杖")),
    ("content-object:spear", ("长枪", "长矛")),
    ("effect-type:wind-tunnel", ("风穴吸引", "风穴效果")),
    ("effect-type:fox-fire", ("狐火",)),
    ("effect-type:transformation", ("变身效果", "变化效果")),
    ("costume-state:without-fire-rat-robe", ("未穿火鼠裘", "脱下火鼠裘")),
    ("scene-energy:quiet", ("安静", "幽静", "寂静", "沉默")),
    ("scene-energy:dialogue", ("交谈", "对话", "说话")),
    ("scene-energy:action", ("追逐", "奔跑", "战斗", "攻击")),
    ("scene-energy:impact", ("冲击", "爆发", "猛力挥刀")),
    ("scene-family:settlement", ("村庄", "乡村", "聚落", "村界")),
    (
        "background:nature",
        (
            "山路",
            "道路",
            "岔路",
            "丘陵",
            "山脊",
            "山麓",
            "森林",
            "草地",
            "树林",
            "湖边",
            "野外",
            "深山",
            "山间",
            "山林",
            "密林",
            "溪谷",
        ),
    ),
    (
        "background:architecture",
        (
            "宅邸",
            "府邸",
            "内室",
            "缘侧",
            "木廊",
            "寺庙",
            "屋檐",
            "檐下",
            "屋顶",
            "木屋",
            "走廊",
            "神社",
            "鸟居",
        ),
    ),
    ("background:night", ("夜景", "夜晚", "夜间", "深夜", "雨夜", "夜空")),
    ("background:interior", ("室内", "内室", "房间", "榻榻米")),
    ("background:courtyard", ("庭院", "院落")),
    ("background:shrine", ("神社", "鸟居")),
    ("background:graveyard", ("墓地", "墓园", "墓碑群")),
    ("effect-type:wind", ("微风", "风中", "迎风", "随风", "风吹")),
    ("effect-type:rain", ("下雨", "雨夜", "雨中", "降雨")),
    ("effect-type:mist", ("雾气", "薄雾", "迷雾", "浓雾", "雾中", "雾里")),
    ("effect-type:snow", ("下雪", "雪中", "降雪", "落雪")),
    (
        "effect-type:snow-light",
        ("刚刚开始下雪", "刚开始下雪", "初雪", "零星雪花", "稀疏雪花"),
    ),
    ("effect-type:snow-heavy", ("暴雪", "大雪", "风雪", "密集雪花")),
    ("effect-type:speed-lines", ("速度线", "动势线")),
    ("effect-type:impact", ("冲击线", "撞击", "爆裂")),
    ("effect-type:aura", ("灵力", "妖气", "光环")),
    ("view-angle:front", ("正面", "正视镜头")),
    ("view-angle:three-quarter-front", ("三分之二侧脸", "四分之三正面")),
    ("view-angle:profile", ("侧脸", "侧面", "侧身")),
    ("view-angle:three-quarter-back", ("三分之二背面", "侧后方")),
    ("view-angle:back", ("背影", "背面", "背对镜头")),
    ("view-angle:high-angle", ("俯视", "高机位")),
    ("view-angle:low-angle", ("仰视", "低机位")),
    ("perspective-risk:high", ("强透视", "大透视", "夸张透视")),
    ("suitable-for:close-up", ("近景", "特写", "胸像")),
    ("suitable-for:two-shot", ("双人构图", "两人同框", "双人关系")),
    ("suitable-for:full-body", ("全身", "完整站姿")),
    ("suitable-for:back-view", ("背影", "背面", "背对镜头")),
    ("suitable-for:weapon-mount", ("佩刀", "佩挂", "刀鞘", "后腰佩带")),
    ("suitable-for:garment-overlap", ("衣物遮挡", "袖子遮挡", "宽袖结构")),
    ("suitable-for:ground-contact", ("接地", "双脚站稳", "脚踩地面")),
)

INTENT_TRAIT_SUPERSEDES = {
    "action:embrace-from-behind": {"action:embrace"},
    "action:draw-weapon": {"action:hold"},
    "action:swing-weapon": {"action:hold"},
    "action:crouch": {"action:sit", "action:kneel"},
    "effect-type:snow-light": {"effect-type:snow"},
    "effect-type:snow-heavy": {"effect-type:snow"},
}


STYLE_CONFUSION_GROUPS = (
    frozenset({"十六夜", "桔梗", "戈薇"}),
    frozenset({"犬夜叉", "杀生丸"}),
    frozenset({"神乐", "神无"}),
    frozenset({"枫婆婆", "幼年枫"}),
    frozenset({"七宝", "云母", "哞哞"}),
)


def infer_retrieval_traits(text: str) -> list[str]:
    """Map explicit request phrases to controlled retrieval traits.

    These traits are ranking hints only. They never add evidence authority and
    must not silently create a content-reference requirement.
    """
    normalized = " ".join(text.casefold().split())
    if not normalized:
        return []
    inferred: list[str] = []
    for trait, aliases in INTENT_TRAIT_RULES:
        searchable = (
            normalized.replace("战斗服", "")
            if trait == "scene-energy:action"
            else normalized
        )
        if trait in searchable or has_nonnegated_alias(searchable, aliases):
            inferred.append(trait)
    inferred_set = set(inferred)
    for specific, superseded in INTENT_TRAIT_SUPERSEDES.items():
        if specific in inferred_set:
            inferred_set.difference_update(superseded)
    return [trait for trait in inferred if trait in inferred_set]


def style_conflict_subjects(text: str) -> set[str]:
    """Return high-confusion subjects absent from the rendering request.

    Current character-style retrieval excludes unrequested characters before
    ranking. These penalties remain explainable compatibility signals for
    non-character-style and historical callers, never identity authority.
    """
    requested = infer_subjects(text)
    conflicts: set[str] = set()
    for group in STYLE_CONFUSION_GROUPS:
        if requested.intersection(group):
            conflicts.update(group.difference(requested))
    return conflicts


def retrieval_traits_for(
    text: str,
    shot: str | None = None,
    existing: Iterable[str] = (),
    medium: str | None = None,
) -> list[str]:
    """Normalize request text and an explicit shot into one ordered trait list."""
    traits = list(dict.fromkeys([*existing, *infer_retrieval_traits(text)]))
    shot_trait = {
        "profile": "view-angle:profile",
        "back-view": "view-angle:back",
    }.get(shot or "")
    if shot_trait and shot_trait not in traits:
        traits.append(shot_trait)
    scene_cues = {
        trait
        for trait in traits
        if trait.startswith(SCENE_ECONOMY_CUE_PREFIXES)
    }
    environment_dominant = (
        shot == "wide-shot"
        or len(scene_cues) >= 2
        or (
            shot in {"medium-shot", "full-body", "two-shot", "group-shot"}
            and bool(scene_cues)
        )
    )
    if environment_dominant and medium == "manga":
        for trait in (
            "scene-economy:authored-negative-space",
            "detail-falloff:strong",
        ):
            if trait not in traits:
                traits.append(trait)
    return traits


def eligible_reference_roles(
    source_roles: Iterable[str], tags: Iterable[str]
) -> list[str]:
    """Return source roles narrowed by an explicit item-level authority tag."""
    tagged_roles = [REFERENCE_ROLE_TAGS[tag] for tag in tags if tag in REFERENCE_ROLE_TAGS]
    if not tagged_roles:
        return sorted(set(source_roles), key=str.casefold)
    return sorted(set(source_roles).intersection(*tagged_roles), key=str.casefold)


def retrieval_relevance(
    item: dict[str, Any],
    *,
    query_terms: Iterable[str] = (),
    exact_terms: Iterable[str] = (),
    subjects: Iterable[str] = (),
    subject_forms: Iterable[tuple[str, str]] = (),
    preferred_subject_forms: Iterable[tuple[str, str]] = (),
    shots: Iterable[str] = (),
    view_angles: Iterable[str] = (),
    folders: Iterable[str] = (),
    contents: Iterable[str] = (),
    penalized_subjects: Iterable[str] = (),
    role: str | None = None,
    shot_weight: int = 4,
) -> tuple[int, list[str]]:
    """Score explicit field matches and explain why a candidate ranked highly."""
    subjects = list(subjects)
    subject_forms = list(subject_forms)
    preferred_subject_forms = list(preferred_subject_forms)
    shots = list(shots)
    view_angles = list(view_angles)
    tags = {str(value).casefold() for value in item.get("tags", [])}
    filename_terms = {
        str(value).casefold() for value in item.get("filename_terms", [])
    }
    item_subjects = {str(value).casefold() for value in item.get("subjects", [])}
    item_forms = {
        str(subject).casefold(): {str(value).casefold() for value in forms}
        for subject, forms in item.get("subject_forms", {}).items()
    }
    item_shots = {str(value).casefold() for value in item.get("shot_types", [])}
    item_folders = {str(value).casefold() for value in item.get("folder_tags", [])}
    content_label = str(item.get("content_label", "")).casefold()
    relative_path = str(item.get("relative_path", "")).casefold()
    note = str(item.get("note", "")).casefold()
    eligible_roles = {str(value).casefold() for value in item.get("eligible_roles", [])}

    score = 0
    reasons: list[str] = []

    if role and role.casefold() in eligible_roles:
        reasons.append(f"eligible role: {role}")
    for subject, form in subject_forms:
        if form.casefold() in item_forms.get(subject.casefold(), set()):
            score += 12
            reasons.append(f"subject-form exact: {subject}={form}")
    for subject in subjects:
        if subject.casefold() in item_subjects:
            score += 8
            reasons.append(f"subject exact: {subject}")
    preferred_exact: list[tuple[str, str]] = []
    preferred_subjects: list[str] = []
    for subject, form in preferred_subject_forms:
        subject_key = subject.casefold()
        if form.casefold() in item_forms.get(subject_key, set()):
            preferred_exact.append((subject, form))
        elif subject_key in item_subjects:
            preferred_subjects.append(subject)
    if preferred_exact:
        # Character-style retrieval should prefer an exact focal character-form
        # over an unrelated image that only matches the requested shot.  Keep
        # the boost capped once so multi-character requests do not turn style
        # evidence into identity evidence.
        score += 5
        reasons.extend(
            f"preferred subject-form exact: {subject}={form}"
            for subject, form in preferred_exact
        )
    elif preferred_subjects:
        score += 1
        reasons.extend(
            f"preferred subject present: {subject}" for subject in preferred_subjects
        )
    if preferred_subject_forms:
        requested_subject_keys = {
            subject.casefold() for subject, _ in preferred_subject_forms
        }
        known_subject_keys = {subject.casefold() for subject in KNOWN_SUBJECTS}
        extra_subject_keys = (
            item_subjects.intersection(known_subject_keys) - requested_subject_keys
        )
        if extra_subject_keys:
            # A panel containing the focal character remains eligible as general
            # rendering evidence, but a focused panel should be inspected first.
            # Apply one capped penalty so multi-character requests are not
            # distorted by the number of co-occurring background characters.
            score -= 2
            reasons.append("preferred subject focus: extra subjects present")
    for shot in shots:
        if shot.casefold() in item_shots:
            score += shot_weight
            reasons.append(f"shot exact: {shot}")
    requested_view_angles = {
        str(value).casefold() for value in view_angles if str(value).strip()
    }
    known_subject_keys = {subject.casefold() for subject in CHARACTER_SUBJECTS}
    view_angle_subject_ambiguous = (
        len(item_subjects.intersection(known_subject_keys)) > 1
    )
    item_view_angles = {
        tag.removeprefix("view-angle:")
        for tag in tags
        if tag.startswith("view-angle:")
    }
    for view_angle in requested_view_angles:
        shot_alias = VIEW_ANGLE_SHOT_MAP.get(view_angle)
        exact_view = view_angle in item_view_angles or (
            shot_alias is not None and shot_alias in item_shots
        )
        if exact_view and not view_angle_subject_ambiguous:
            # View applicability matters more than camera distance for
            # identity-bearing face, bangs, jaw, and hair mark-making.
            score += 12
            reasons.append(f"view angle exact: {view_angle}")
        elif exact_view:
            reasons.append(
                f"view angle ambiguous across co-occurring subjects: {view_angle}"
            )
        elif item_view_angles and "multi-view" not in item_view_angles:
            score -= 8
            reasons.append(f"view angle mismatch: {view_angle}")
    for folder in folders:
        if folder.casefold() in item_folders:
            score += 3
            reasons.append(f"folder exact: {folder}")
    for content in contents:
        if content.casefold() == content_label:
            score += 8
            reasons.append(f"content exact: {content}")
    for subject in penalized_subjects:
        if subject.casefold() in item_subjects:
            score -= 6
            reasons.append(f"style identity conflict penalty: {subject}")

    def tag_weight(term: str) -> int:
        if term.startswith("scene-id:"):
            return 12
        if term.startswith("scene-family:"):
            return 12
        if term.startswith(("action:", "content-object:", "subject-object:")):
            return 9
        if term.startswith("interaction:"):
            return 7
        if term.startswith(("contact-type:", "prop-attachment:")):
            return 5
        if term.startswith(("expression:", "view-angle:", "suitable-for:")):
            return 4
        if term.startswith(("background:", "effect-type:", "scene-energy:")):
            return 2
        if term.startswith(("scene-economy:", "detail-falloff:")):
            return 4
        return 6

    scored_terms: set[str] = set()
    for raw_term in [*exact_terms, *query_terms]:
        term = raw_term.casefold().strip()
        if not term or term in scored_terms:
            continue
        scored_terms.add(term)
        if term in tags:
            weight = tag_weight(term)
            score += weight
            reasons.append(f"tag exact: {raw_term}")
        elif term in filename_terms:
            score += 8
            reasons.append(f"filename term exact: {raw_term}")
        elif term == content_label:
            score += 8
            reasons.append(f"content exact: {raw_term}")
        elif term in item_folders:
            score += 3
            reasons.append(f"folder exact: {raw_term}")
        elif term in relative_path:
            score += 1
            reasons.append(f"path contains: {raw_term}")
        elif term in note:
            score += 1
            reasons.append(f"note contains: {raw_term}")
    return score, reasons


def certified_style_anchor_rank(
    item: dict[str, Any], *, role: str | None, reference_domain: str | None
) -> int:
    """Prefer inspected style anchors only after ordinary relevance ties."""
    if role != "rendering" or reference_domain not in {"character-style", "scene"}:
        return 0
    return int("style-anchor:certified" in set(item.get("tags") or []))


def infer_structured_metadata(path: Path, source: dict[str, Any]) -> dict[str, Any]:
    """Extract stable retrieval facets from folders and a lightweight filename grammar."""
    _, _, folder_tags = folder_metadata(path)
    searchable = " ".join([*folder_tags, path.stem])
    subjects = infer_subjects(searchable)
    relative = path.as_posix()
    subject_form_override = source.get("path_subject_form_overrides", {}).get(
        relative
    )
    if subject_form_override is not None:
        # Exact-path overrides are complete replacements.  This lets a visually
        # inspected sheet add an unmentioned co-subject/prop or remove a subject
        # that appears only in a misleading filename.
        subjects = set(subject_form_override)

    forms = {value for token, value in FORM_TOKEN_MAP.items() if token in searchable}
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
    if subject_form_override is not None:
        forms = paired_forms
    elif paired_forms:
        forms = paired_forms

    shot_types = {
        value for token, value in SHOT_TOKEN_MAP.items() if token in searchable
    }
    character_count = len(subjects & CHARACTER_SUBJECTS)
    if character_count == 2:
        shot_types.add("two-shot")
    elif character_count > 2:
        shot_types.add("group-shot")
    shot_override = source.get("path_shot_overrides", {}).get(relative)
    if shot_override is not None:
        shot_types = set(shot_override)

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
    # Filenames and folders are structured evidence, not free-text notes. Map
    # their explicit wording through the same controlled vocabulary used for
    # request intent so assets such as 山间寺庙 or 雨中屋顶 remain retrievable
    # without duplicating those observable facts in manual annotations.
    tags.update(infer_retrieval_traits(searchable))
    structured = infer_structured_metadata(path, source)
    for field, values in structured.items():
        if field == "subject_forms":
            for subject, forms in values.items():
                tags.add(subject)
                tags.update(forms)
            continue
        tags.update(values)
    tags.difference_update(
        source.get("path_tag_suppressions", {}).get(path.as_posix(), [])
    )
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
