#!/usr/bin/env python3
"""Normalize legacy manga screenshot filenames into searchable structured fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from workflow_common import IMAGE_EXTENSIONS, atomic_write_json

DEFAULT_ROOT = Path(
    "/Users/jquery/Documents/inuYasha-design/origin-photos/manga-photos"
)
DEFAULT_MANIFEST_DIR = Path(
    "/Users/jquery/Documents/inuYasha-design/reference-workflow/rename-manifests"
)
SUBJECT_NAMES = (
    "枫婆婆",
    "戈薇爷爷",
    "食骨之井",
    "普通人物",
    "杀生丸",
    "犬夜叉",
    "刀刀斋",
    "十六夜",
    "铁碎牙",
    "天生牙",
    "幼年枫",
    "桔梗",
    "戈薇",
    "弥勒",
    "珊瑚",
    "七宝",
    "云母",
    "邪见",
    "琥珀",
    "钢牙",
    "神乐",
    "神无",
    "冥加",
    "草太",
    "和尚",
    "玲",
)
NON_CHARACTER_SUBJECTS = {"铁碎牙", "天生牙", "食骨之井", "场景"}
COMPLIANT_NAME = re.compile(r"^[^_]+__[^_]+__[^_]+__[^_]+__\d{2}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_sequence(stem: str) -> tuple[str, int]:
    match = re.search(r"(\d{1,3})$", stem)
    if not match:
        return stem, 1
    return stem[: match.start()], int(match.group(1))


def ordered_subjects(text: str) -> list[str]:
    found = []
    for name in SUBJECT_NAMES:
        position = text.find(name)
        if position >= 0:
            found.append((position, name))
    return [name for _, name in sorted(found)]


def classify(path: Path, root: Path) -> str:
    stem, sequence = split_sequence(path.stem)
    folder = path.parent.name
    subjects = ordered_subjects(stem)
    folder_subjects = ordered_subjects(folder)
    if folder == "场景":
        subjects = ["场景"]
    elif not subjects:
        subjects = folder_subjects or [folder]
    elif "人类形态" in stem and "犬夜叉" in folder_subjects:
        subjects = ["犬夜叉", *subjects]
    subjects = list(dict.fromkeys(subjects))

    if "人类形态" in stem:
        form = "人类形态"
    elif "幼年形态" in stem or "幼年" in stem:
        form = "幼年形态"
    elif "半全妖形态" in stem or "全妖形态" in stem:
        form = "全妖形态"
    elif set(subjects) <= NON_CHARACTER_SUBJECTS:
        form = "不适用"
    else:
        form = "默认形态"

    character_subjects = [
        subject for subject in subjects if subject not in NON_CHARACTER_SUBJECTS
    ]
    if "上半身" in stem or "上身" in stem:
        shot = "上身"
    elif "侧脸" in stem:
        shot = "侧脸"
    elif "侧身" in stem:
        shot = "侧身"
    elif "全身" in stem:
        shot = "全身"
    elif len(character_subjects) >= 2:
        shot = "双人" if len(character_subjects) == 2 else "群像"
    elif subjects == ["场景"]:
        shot = "远景"
    elif set(subjects) <= NON_CHARACTER_SUBJECTS:
        shot = "细节"
    elif any(subject in NON_CHARACTER_SUBJECTS for subject in subjects):
        shot = "动作"
    else:
        shot = "近景"

    if subjects == ["场景"]:
        content = stem
    elif "未变化" in stem and "铁碎牙" in stem:
        content = "未变化铁碎牙"
    elif "变化" in stem and "铁碎牙" in stem:
        content = "变化铁碎牙"
    elif "食骨之井" in stem:
        content = "食骨之井"
    elif "天生牙" in stem:
        content = "天生牙"
    elif len(character_subjects) >= 2:
        content = "同框"
    elif "幼年" in stem:
        content = "幼年参考"
    else:
        content = "人物参考"

    subject_field = "-".join(subjects)
    return f"{subject_field}__{form}__{shot}__{content}__{sequence:02d}{path.suffix}"


def build_plan(root: Path) -> list[dict[str, str]]:
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and not any(part.startswith(".") for part in path.relative_to(root).parts)
        ),
        key=lambda path: str(path.relative_to(root)).casefold(),
    )
    plan = []
    targets: set[Path] = set()
    for path in files:
        if COMPLIANT_NAME.fullmatch(path.stem):
            target = path
        else:
            target = path.with_name(classify(path, root))
        if target in targets:
            raise ValueError(f"rename collision: {target}")
        targets.add(target)
        if target.exists() and target != path:
            raise ValueError(f"target already exists: {target}")
        plan.append(
            {
                "old": str(path.relative_to(root)),
                "new": str(target.relative_to(root)),
                "sha256": file_hash(path),
                "changed": path != target,
            }
        )
    return plan


def apply_plan(root: Path, plan: list[dict[str, str]]) -> None:
    changed = [row for row in plan if row["changed"]]
    staged: list[tuple[Path, Path, Path]] = []
    try:
        for index, row in enumerate(changed, 1):
            old = root / row["old"]
            new = root / row["new"]
            temporary = old.with_name(
                f".__codex-rename-{index:04d}-{old.stem}{old.suffix}"
            )
            if temporary.exists():
                raise ValueError(f"temporary target already exists: {temporary}")
            old.rename(temporary)
            staged.append((old, temporary, new))
        completed = 0
        try:
            for _, temporary, new in staged:
                temporary.rename(new)
                completed += 1
        except Exception:
            for old, _, new in reversed(staged[:completed]):
                new.rename(old)
            for old, temporary, _ in reversed(staged[completed:]):
                temporary.rename(old)
            raise
    except Exception:
        for old, temporary, _ in reversed(staged):
            if temporary.exists() and not old.exists():
                temporary.rename(old)
        raise


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"missing source root: {root}")
    plan = build_plan(root)
    result = {
        "root": str(root),
        "mode": "apply" if args.apply else "dry-run",
        "file_count": len(plan),
        "rename_count": sum(row["changed"] for row in plan),
        "unchanged_count": sum(not row["changed"] for row in plan),
        "renames": plan,
    }
    if args.apply:
        apply_plan(root, plan)
        result["status"] = "complete"
        manifest = args.manifest or (
            DEFAULT_MANIFEST_DIR
            / f"manga-photos-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}.json"
        )
        atomic_write_json(manifest.expanduser().resolve(), result)
        result["manifest"] = str(manifest.expanduser().resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for row in plan:
            if row["changed"]:
                print(f"{row['old']} -> {row['new']}")
        print(
            f"{result['mode']}: {result['rename_count']} renamed, "
            f"{result['unchanged_count']} unchanged"
        )
        if result.get("manifest"):
            print(result["manifest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
