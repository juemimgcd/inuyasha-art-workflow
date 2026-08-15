#!/usr/bin/env python3
"""Create a compact accepted-result microfix or recorded-candidate local edit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from prepare_reference_set import file_hash, parse_box, validate_crop_box
from task_workflow import (
    CHANGE_CATEGORIES,
    read_json,
    result_output,
    write_compiled_prompt,
)
from workflow_common import (
    atomic_write_json,
    atomic_write_text,
    load_config,
    resolve_recorded_path,
    workflow_paths,
    workflow_root,
)

SCRIPTS = Path(__file__).resolve().parent


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def inherited_reference_arguments(entry: dict) -> list[str]:
    item_id = entry["item_id"]
    arguments = ["--select", f"{entry['role']}={item_id}"]
    crop_box = entry.get("crop_box")
    focus = entry.get("focus")
    if crop_box:
        coordinates = ",".join(str(value) for value in crop_box)
        arguments.extend(["--crop", f"{item_id}={coordinates}"])
    if focus:
        arguments.extend(["--focus", f"{item_id}={focus}"])
    return arguments


def context_box_for(
    edit_box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    validate_crop_box(edit_box, image_size)
    x, y, width, height = edit_box
    image_width, image_height = image_size
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(image_width, x + width + padding)
    bottom = min(image_height, y + height + padding)
    return left, top, right - left, bottom - top


def continuation_intent(candidate_source: dict | None, full_canvas: bool) -> str:
    return "edit" if candidate_source or full_canvas else "microfix"


def recorded_attempt_source(parent: Path, selector: str) -> tuple[Path, dict]:
    """Resolve one immutable candidate output and verify its recorded hash."""
    attempts_root = parent / "attempts"
    attempt_paths = sorted(attempts_root.glob("*/attempt.json"))
    if not attempt_paths:
        raise SystemExit("Parent task has no recorded candidate attempts")
    if selector == "latest":
        attempt_path = next(
            (
                path
                for path in reversed(attempt_paths)
                if read_json(path).get("status") in {"accepted", "rejected"}
            ),
            None,
        )
        if attempt_path is None:
            raise SystemExit("Parent task has no recorded image candidate attempt")
    else:
        try:
            number = int(selector)
        except ValueError as exc:
            raise SystemExit(
                "--from-attempt must be a positive number or 'latest'"
            ) from exc
        if number < 1:
            raise SystemExit("--from-attempt must be a positive number or 'latest'")
        attempt_path = attempts_root / f"{number:03d}" / "attempt.json"
    if not attempt_path.is_file():
        raise SystemExit(f"Recorded attempt is missing: {attempt_path}")

    attempt = read_json(attempt_path)
    if attempt.get("status") not in {"accepted", "rejected"}:
        raise SystemExit(
            "Candidate local edits require an accepted or rejected image attempt"
        )
    output_text = attempt.get("output")
    if not output_text:
        raise SystemExit("Recorded candidate attempt has no output")
    target = resolve_recorded_path(output_text)
    if not target.is_file():
        raise SystemExit(f"Recorded candidate output is missing: {target}")
    output_hash = file_hash(target)
    recorded_hash = attempt.get("output_sha256")
    if not recorded_hash or output_hash != recorded_hash:
        raise SystemExit("Recorded candidate output hash does not match attempt.json")
    return target, {
        "task_id": parent.name,
        "attempt": attempt.get("attempt"),
        "status": attempt.get("status"),
        "output": str(target),
        "output_sha256": output_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--from-task", type=Path, required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--change-category", choices=CHANGE_CATEGORIES, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument(
        "--from-attempt",
        metavar="NUMBER|latest",
        help=(
            "Use a recorded candidate from --from-task as a local edit target. "
            "Requires --edit-box or --full-canvas and creates an edit task without "
            "accepting the candidate."
        ),
    )
    parser.add_argument(
        "--full-canvas",
        action="store_true",
        help=(
            "Create a tracked full-canvas edit when the requested change crosses a "
            "safe crop boundary. Prefer --edit-box for bounded follow-up feedback."
        ),
    )
    parser.add_argument("--inherit-style", action="store_true")
    parser.add_argument("--inherit-identity", action="store_true")
    parser.add_argument(
        "--target-max-edge",
        type=int,
        default=960,
        help="Transport proxy maximum edge for a full-canvas target (default: 960).",
    )
    parser.add_argument(
        "--use-original-target",
        action="store_true",
        help="Use the original full-canvas target instead of a transport proxy.",
    )
    parser.add_argument(
        "--edit-box",
        type=parse_box,
        metavar="X,Y,WIDTH,HEIGHT",
        help=(
            "Use crop-and-composite mode for this exact target-image region. "
            "Coordinates are pixels in the accepted parent output."
        ),
    )
    parser.add_argument(
        "--context-padding",
        type=int,
        default=96,
        help="Context pixels around --edit-box (default: 96).",
    )
    args = parser.parse_args()
    if args.from_attempt and args.target:
        raise SystemExit("--from-attempt cannot be combined with --target")
    if args.edit_box and args.full_canvas:
        raise SystemExit("--edit-box and --full-canvas are mutually exclusive")
    if args.from_attempt and not (args.edit_box or args.full_canvas):
        raise SystemExit("--from-attempt requires --edit-box or --full-canvas")
    if args.context_padding < 0:
        raise SystemExit("--context-padding must be zero or greater")
    if args.target_max_edge < 256:
        raise SystemExit("--target-max-edge must be at least 256")

    config = load_config()
    root = workflow_root(config, args.workflow_root)
    parent = args.from_task.expanduser().resolve()
    if parent.parent != workflow_paths(root)["tasks"].resolve():
        raise SystemExit(
            "--from-task must be directly under the workflow tasks directory"
        )
    if (parent / "archived.json").is_file():
        raise SystemExit("Archived tasks cannot be used as microfix parents")
    brief = read_json(parent / "brief.json")
    manifest = read_json(parent / "reference-manifest.json")
    candidate_source = None
    result = None
    if args.from_attempt:
        target, candidate_source = recorded_attempt_source(parent, args.from_attempt)
    else:
        result = read_json(parent / "result.json")
        target = (
            args.target.expanduser().resolve() if args.target else result_output(result)
        )
    if target is None or not target.is_file():
        raise SystemExit("Parent accepted output or --target is missing")

    intent = continuation_intent(candidate_source, args.full_canvas)

    init_command = [
        sys.executable,
        str(SCRIPTS / "init_art_task.py"),
        "--workflow-root",
        str(root),
        "--slug",
        args.slug,
        "--medium",
        brief.get("medium", "manga"),
        "--deliverable",
        "edit",
        "--intent",
        intent,
        "--parent-task",
        str(parent),
        "--change-category",
        args.change_category,
        "--change-request",
        args.change,
        "--request",
        args.change,
    ]
    if brief.get("period_mode"):
        init_command.extend(["--period-mode", brief["period_mode"]])
    task_dir = Path(run(init_command).splitlines()[-1]).resolve()

    local_edit = None
    child_brief_path = task_dir / "brief.json"
    child_brief = read_json(child_brief_path)
    child_brief["prompt_invariants"] = [
        (
            "来源候选图中未被点名的角色身份、形态、构图和漫画画法保持不变"
            if candidate_source
            else "父任务中已经通过的角色身份、形态、构图和漫画画法保持不变"
        ),
        f"只处理 {args.change_category} 类问题，不引入其他设计改动",
    ]
    if candidate_source:
        child_brief["candidate_source"] = candidate_source
    if args.full_canvas:
        child_brief["edit_scope"] = "full-canvas"
        child_brief["prompt_invariants"].append(
            "整图修改只处理点名问题，未点名的构图、角色和背景关系保持不变"
        )
    if args.edit_box:
        from PIL import Image

        with Image.open(target) as target_image:
            context_box = context_box_for(
                args.edit_box, target_image.size, args.context_padding
            )
        edit_x, edit_y, edit_width, edit_height = args.edit_box
        context_x, context_y, _, _ = context_box
        local_edit = {
            "mode": "crop-composite",
            "target": str(target),
            "edit_box": list(args.edit_box),
            "context_box": list(context_box),
            "edit_box_in_context": [
                edit_x - context_x,
                edit_y - context_y,
                edit_width,
                edit_height,
            ],
            "feather_pixels": min(12, max(2, min(edit_width, edit_height) // 20)),
        }
        child_brief["local_edit"] = local_edit
        child_brief["prompt_invariants"].append(
            "生成内容只供声明的编辑框合成，框外像素必须与来源图完全一致"
        )
    atomic_write_json(child_brief_path, child_brief)

    references = manifest.get("references", [])
    selected_entries: list[dict] = []
    needs_identity = args.change_category in {
        "identity",
        "form",
        "costume",
        "anatomy",
        "construction",
    }
    needs_style = args.change_category in {"medium", "tone"}
    if needs_style or args.inherit_style:
        selected_entries.extend(
            entry for entry in references if entry.get("role") == "style"
        )
        selected_entries = selected_entries[:1]
    if needs_identity or args.inherit_identity:
        selected_entries.extend(
            entry for entry in references if entry.get("role") == "identity"
        )

    prepare_command = [
        sys.executable,
        str(SCRIPTS / "prepare_reference_set.py"),
        "--workflow-root",
        str(root),
        "--task-dir",
        str(task_dir),
        "--external",
        f"target={target}",
    ]
    if local_edit:
        prepare_command.extend(
            [
                "--external-target-crop",
                ",".join(str(value) for value in local_edit["context_box"]),
                "--external-target-focus",
                args.change,
            ]
        )
    elif not args.use_original_target:
        prepare_command.extend(
            ["--external-target-max-edge", str(args.target_max_edge)]
        )
    for entry in selected_entries:
        prepare_command.extend(inherited_reference_arguments(entry))
    run(prepare_command)
    if candidate_source:
        child_manifest_path = task_dir / "reference-manifest.json"
        child_manifest = read_json(child_manifest_path)
        target_entry = (child_manifest.get("references") or [None])[0]
        if not target_entry or target_entry.get("role") != "target":
            raise SystemExit("Candidate edit manifest did not place target first")
        target_entry["source_attempt"] = candidate_source
        atomic_write_json(child_manifest_path, child_manifest)
    write_compiled_prompt(task_dir)

    inherited = ", ".join(entry["item_id"] for entry in selected_entries) or (
        "target context crop" if local_edit else "target only"
    )
    inherited_source = (
        "recorded candidate output" if candidate_source else "accepted output"
    )
    local_edit_evidence = ""
    if local_edit:
        local_edit_evidence = f"""
- Local edit mode: `crop-composite`
- Source edit box: `{local_edit["edit_box"]}`
- Prepared context box: `{local_edit["context_box"]}`
- After generation: run `composite_local_microfix.py` before QA and attempt recording.
"""
    evidence = f"""# Evidence log

Task: `{task_dir.name}`
Parent task: `{parent.name}`
Intent: `{intent}`

## Inherited evidence

- Parent task: `{parent.name}`
- Parent medium: `{brief.get("medium")}`
- Identity forms: `{brief.get("identity_forms", {})}`
- Result: `HIT`; inherit the parent's inspected evidence and {inherited_source}.

## Change-specific evidence

- Category: `{args.change_category}`
- Requested change: {args.change}
- Prepared evidence: `{inherited}`
- Result: `HIT`; target controls all unchanged regions. Added references control only their manifest roles.
{local_edit_evidence}
"""
    atomic_write_text(task_dir / "evidence-log.md", evidence)
    print(task_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        print(message, file=sys.stderr)
        raise SystemExit(2)
