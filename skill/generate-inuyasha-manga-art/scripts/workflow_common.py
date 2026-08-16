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
    config = load_json(path)
    if config.get("schema_version") != 1:
        raise ValueError(f"Unsupported source-library schema in {path}")
    if config.get("workflow_root"):
        config["workflow_root"] = str(expand_config_path(config["workflow_root"]))
    for source in config.get("sources", []):
        source["path"] = str(expand_config_path(source["path"]))
    for alias in config.get("path_aliases", []):
        alias["to"] = str(expand_config_path(alias["to"]))
    return config


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
    ("action:swing-weapon", ("挥刀", "挥剑", "挥动铁碎牙", "挥出铁碎牙")),
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
    ("scene-energy:quiet", ("安静", "幽静", "寂静", "沉默")),
    ("scene-energy:dialogue", ("交谈", "对话", "说话")),
    ("scene-energy:action", ("追逐", "奔跑", "战斗", "攻击")),
    ("scene-energy:impact", ("冲击", "爆发", "猛力挥刀")),
    ("background:nature", ("森林", "草地", "树林", "湖边", "野外")),
    (
        "background:architecture",
        ("宅邸", "府邸", "内室", "缘侧", "木廊", "寺庙"),
    ),
    ("background:night", ("夜景", "夜晚", "夜间", "深夜", "雨夜", "夜空")),
    ("background:interior", ("室内", "内室", "房间", "榻榻米")),
    ("background:courtyard", ("庭院", "院落")),
    ("background:shrine", ("神社", "鸟居")),
    ("background:graveyard", ("墓地", "墓园", "墓碑群")),
    ("effect-type:wind", ("微风", "风中", "迎风", "随风", "风吹")),
    ("effect-type:rain", ("下雨", "雨夜", "雨中", "降雨")),
    ("effect-type:mist", ("雾气", "薄雾", "迷雾")),
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
        if trait in normalized or any(alias.casefold() in normalized for alias in aliases):
            inferred.append(trait)
    inferred_set = set(inferred)
    for specific, superseded in INTENT_TRAIT_SUPERSEDES.items():
        if specific in inferred_set:
            inferred_set.difference_update(superseded)
    return [trait for trait in inferred if trait in inferred_set]


def style_conflict_subjects(text: str) -> set[str]:
    """Return high-confusion subjects absent from the rendering request.

    Rendering retrieval stays identity-independent: callers use these only as
    a soft, explainable ranking penalty, never as a filter or identity boost.
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
    if shot == "wide-shot" and medium == "manga":
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
    folders: Iterable[str] = (),
    contents: Iterable[str] = (),
    penalized_subjects: Iterable[str] = (),
    role: str | None = None,
) -> tuple[int, list[str]]:
    """Score explicit field matches and explain why a candidate ranked highly."""
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
        score += 3
        reasons.extend(
            f"preferred subject-form exact: {subject}={form}"
            for subject, form in preferred_exact
        )
    elif preferred_subjects:
        score += 1
        reasons.extend(
            f"preferred subject present: {subject}" for subject in preferred_subjects
        )
    for shot in shots:
        if shot.casefold() in item_shots:
            score += 4
            reasons.append(f"shot exact: {shot}")
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
        if term.startswith(("action:", "content-object:", "subject-object:")):
            return 8
        if term.startswith("interaction:"):
            return 7
        if term.startswith(("contact-type:", "prop-attachment:")):
            return 5
        if term.startswith(("expression:", "view-angle:", "suitable-for:")):
            return 4
        if term.startswith(("background:", "effect-type:", "scene-energy:")):
            return 2
        if term.startswith(("scene-economy:", "detail-falloff:")):
            return 2
        return 6

    for raw_term in [*exact_terms, *query_terms]:
        term = raw_term.casefold().strip()
        if not term:
            continue
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


def infer_structured_metadata(path: Path, source: dict[str, Any]) -> dict[str, Any]:
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
