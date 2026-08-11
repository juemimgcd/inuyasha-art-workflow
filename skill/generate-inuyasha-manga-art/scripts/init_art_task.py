#!/usr/bin/env python3
"""Create a non-destructive art task workspace with evidence and QA records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from task_workflow import (
    BRIEF_SCHEMA_VERSION,
    CHANGE_CATEGORIES,
    DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_MAX_TECHNICAL_RETRIES,
    DEFAULT_NEW_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_POST_GENERATION_TARGET_SECONDS,
    INTENT_VALUES,
    LATENCY_SCHEMA_VERSION,
    compile_prompt,
    read_json,
)
from workflow_common import (
    FORM_VALUES,
    atomic_write_json,
    atomic_write_text,
    ensure_workflow_dirs,
    load_config,
    now_iso,
    slugify,
    workflow_root,
)

BASE_QA_ITEMS = [
    ("identity", "角色名称、年龄或形态正确"),
    ("identity", "发型、脸部标志、服装层次和相对体型正确"),
    ("identity", "手、耳朵、饰品、武器和道具保持身份关键形状"),
    ("medium", "目标媒介占主导且没有非目标媒介泄漏"),
    ("medium", "线条、网点或赛璐璐阴影符合所选视觉模式"),
    ("composition", "焦点层级清楚，动作方向和剪影可读"),
    ("composition", "背景细节没有与焦点角色竞争"),
    ("construction", "人物、道具与背景使用一致的前后层级、透视方向和相对尺度"),
    ("construction", "身体接触、地面接触、衣物遮挡和道具承重连接连续且无悬浮穿模"),
    ("technical", "没有非要求文字、对话框、签名、logo 或水印"),
    ("technical", "成图比例与交付物类型符合 brief"),
    ("process", "实际使用的参考图与 reference-manifest.json 一致"),
]


def qa_items(
    medium: str, intent: str = "new", change_category: str | None = None
) -> list[tuple[str, str]]:
    source_check = (
        "漫画风格截图只控制画法，没有复制其人物、文字、分镜或剧情"
        if medium == "manga"
        else "TV 截图只控制配色与动画画法，没有复制其构图、人物或剧情"
    )
    full = [
        *BASE_QA_ITEMS[:-1],
        ("process", source_check),
        (
            "process",
            "selected-output 只控制已认可的连续性和完成度，没有覆盖官方身份或目标媒介画法",
        ),
        (
            "process",
            "跨媒介 content 只控制清单中点名的可见内容，未泄漏来源媒介的配色、线条、阴影、背景或角色画法",
        ),
        BASE_QA_ITEMS[-1],
    ]
    if intent != "microfix":
        return full
    category = change_category or "polish"
    checks = [
        (category, f"仅修改指定的 {category} 问题，修改结果符合请求"),
        ("preservation", "目标区域以外的人物、构图、画法和背景保持不变"),
        ("identity", "局部编辑没有造成角色身份、形态或服装漂移"),
    ]
    if category in {"construction", "costume", "anatomy", "composition"}:
        checks.append(
            (
                "construction",
                "修改区域的连接、遮挡、透视和接地关系连续，没有悬浮或穿模",
            )
        )
    return [
        *checks,
        ("technical", "没有非要求文字、对话框、签名、logo 或水印"),
        ("technical", "成图比例与目标图保持一致"),
        ("process", "实际使用的参考图与 reference-manifest.json 一致"),
    ]


def parse_identity_form(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("identity form must look like CHARACTER=FORM")
    character, form = (part.strip() for part in value.split("=", 1))
    if not character:
        raise argparse.ArgumentTypeError("character cannot be empty")
    if form not in FORM_VALUES:
        raise argparse.ArgumentTypeError(
            f"form must be one of: {', '.join(FORM_VALUES)}"
        )
    return character, form


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--medium", choices=("manga", "tv"), required=True)
    parser.add_argument(
        "--deliverable",
        choices=("illustration", "manga-page", "character-sheet", "edit"),
        default="illustration",
    )
    parser.add_argument("--request", required=True)
    parser.add_argument("--intent", choices=INTENT_VALUES)
    parser.add_argument("--parent-task", type=Path)
    parser.add_argument("--change-category", choices=CHANGE_CATEGORIES)
    parser.add_argument("--change-request")
    parser.add_argument("--aspect-ratio", default="2:3 portrait")
    parser.add_argument(
        "--period-mode", choices=("early-rounded", "classic-balanced", "late-action")
    )
    parser.add_argument(
        "--identity-form",
        type=parse_identity_form,
        action="append",
        default=[],
        metavar="CHARACTER=FORM",
        help="Declare a required form for identity-reference compatibility.",
    )
    parser.add_argument(
        "--content-query",
        default="",
        help="Terms for a separately scoped content-evidence search.",
    )
    parser.add_argument(
        "--content-focus",
        default="",
        help="Exact visible content a content reference may control.",
    )
    parser.add_argument(
        "--content-provenance",
        choices=("observed-content", "fallback-medium-original"),
        default="observed-content",
        help=(
            "Label genuinely fallback-medium-original content so it is not "
            "presented as selected-medium canon."
        ),
    )
    parser.add_argument(
        "--pre-generation-target-seconds",
        type=int,
        help="Soft target for controllable preparation; defaults by intent.",
    )
    parser.add_argument(
        "--post-generation-target-seconds",
        type=int,
        default=DEFAULT_POST_GENERATION_TARGET_SECONDS,
        help="Soft target for blocking inspection and handoff (default: 30).",
    )
    parser.add_argument(
        "--response-slo-seconds",
        type=int,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    intent = args.intent or ("edit" if args.deliverable == "edit" else "new")
    pre_generation_target = args.pre_generation_target_seconds or (
        DEFAULT_NEW_PRE_GENERATION_TARGET_SECONDS
        if intent == "new"
        else DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS
    )
    if pre_generation_target < 1 or args.post_generation_target_seconds < 1:
        raise SystemExit("phase targets must be positive integers")
    parent_brief = None
    parent_task_id = None
    if args.parent_task:
        parent_task = args.parent_task.expanduser().resolve()
        if not (parent_task / "brief.json").is_file():
            raise SystemExit("--parent-task must contain brief.json")
        parent_brief = read_json(parent_task / "brief.json")
        parent_task_id = parent_brief.get("task_id") or parent_task.name
    if intent == "microfix" and parent_brief is None:
        raise SystemExit("microfix tasks require --parent-task")
    if intent == "microfix" and not args.change_request:
        raise SystemExit("microfix tasks require --change-request")
    if intent == "microfix" and not args.change_category:
        raise SystemExit("microfix tasks require --change-category")
    if parent_brief and parent_brief.get("medium") != args.medium:
        raise SystemExit("Parent and child tasks must use the same medium")
    content_query = args.content_query.strip()
    content_focus = args.content_focus.strip()
    if bool(content_query) != bool(content_focus):
        raise SystemExit(
            "--content-query and --content-focus must be supplied together"
        )
    if not content_query and args.content_provenance != "observed-content":
        raise SystemExit("--content-provenance requires a planned content query")
    period_mode = (
        args.period_mode
        or (parent_brief or {}).get("period_mode")
        or ("classic-balanced" if args.medium == "manga" else None)
    )
    root = workflow_root(config, args.workflow_root)
    paths = ensure_workflow_dirs(root)
    date_prefix = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
    task_id = f"{date_prefix}-{slugify(args.slug)}"
    task_dir = paths["tasks"] / task_id
    if task_dir.exists():
        raise SystemExit(f"Task already exists; choose another slug: {task_dir}")
    (task_dir / "references").mkdir(parents=True)
    (task_dir / "outputs").mkdir()

    inherited_forms = (parent_brief or {}).get("identity_forms") or {}
    supplied_forms = dict(args.identity_form)
    if len(supplied_forms) != len(args.identity_form):
        raise SystemExit("Each character may have only one --identity-form")
    identity_forms = supplied_forms or dict(inherited_forms)
    if parent_brief and supplied_forms and identity_forms != inherited_forms:
        raise SystemExit("A continuation cannot silently change parent identity forms")
    inherited_invariants = list((parent_brief or {}).get("invariants") or [])
    supplied_content_need = (
        {
            "query": content_query,
            "focus": content_focus,
            "selected_medium_source": (
                "manga-curated" if args.medium == "manga" else "tv-curated"
            ),
            "fallback_source": (
                "tv-curated" if args.medium == "manga" else "manga-curated"
            ),
            "provenance": args.content_provenance,
        }
        if content_query
        else {}
    )
    content_need = supplied_content_need or dict(
        (parent_brief or {}).get("content_need") or {}
    )
    created_at = now_iso()
    brief = {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "task_id": task_id,
        "created_at": created_at,
        "request": args.request,
        "intent": intent,
        "parent_task_id": parent_task_id,
        "change_category": args.change_category,
        "change_request": args.change_request or "",
        "medium": args.medium,
        "deliverable": args.deliverable,
        "period_mode": period_mode,
        "style_strategy": f"two-layer-{args.medium}-fast",
        "style_references": [],
        "content_need": content_need,
        "content_references": [],
        "characters": list(identity_forms),
        "identity_forms": identity_forms,
        "forms_and_costumes": [
            f"{character}: {form}" for character, form in identity_forms.items()
        ],
        "scene": (parent_brief or {}).get("scene", ""),
        "aspect_ratio": ((parent_brief or {}).get("aspect_ratio") or args.aspect_ratio),
        "invariants": inherited_invariants,
        "latency_budget": {
            "schema_version": LATENCY_SCHEMA_VERSION,
            "pre_generation_target_seconds": pre_generation_target,
            "post_generation_target_seconds": args.post_generation_target_seconds,
            "max_technical_retries": DEFAULT_MAX_TECHNICAL_RETRIES,
            "generation_latency_policy": "observe-only",
        },
    }
    atomic_write_json(task_dir / "brief.json", brief)
    atomic_write_json(
        task_dir / "reference-manifest.json", {"schema_version": 1, "references": []}
    )
    atomic_write_json(
        task_dir / "qa.json",
        {
            "schema_version": 1,
            "status_values": ["pending", "pass", "fail", "n/a"],
            "checks": [
                {"category": category, "check": check, "status": "pending", "note": ""}
                for category, check in qa_items(
                    args.medium, intent, args.change_category
                )
            ],
        },
    )
    if intent == "microfix":
        evidence = f"""# Evidence log

Task: `{task_id}`
Parent task: `{parent_task_id}`
Intent: `microfix`

The parent task's inspected identity and manga evidence remain authoritative while the catalog and character forms are unchanged. Re-open only the layer required by the named change category.

## Inherited evidence

- Parent task: `{parent_task_id}`
- Identity forms: `{identity_forms}`
- Result: `HIT` inherited from the validated parent task.

## Change-specific evidence

- Category: `{args.change_category}`
- Requested change: {args.change_request}
- Additional source: `N/A` unless a new detail reference is prepared.
- Result: `HIT` from target continuity; inspect any added reference before generation.
"""
    else:
        selected_content_source = (
            "manga-curated" if args.medium == "manga" else "tv-curated"
        )
        fallback_content_source = (
            "tv-curated" if args.medium == "manga" else "manga-curated"
        )
        content_need_text = content_need.get("focus") or "N/A"
        content_query_text = content_need.get("query") or "N/A"
        selected_content_result = "" if content_need else "SKIP"
        fallback_content_result = "" if content_need else "SKIP"
        evidence = f"""# Evidence log

Task: `{task_id}`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need:
- Source searched:
- Result:
- Selected item IDs:
- Usable evidence:

## Layer 2: Manga or TV screenshots

- Need:
- Source browsed:
- Selected item IDs:
- Result:
- Controls:
- Must not control:

## Layer 3: exact content evidence

- Need: {content_need_text}
- Query: {content_query_text}
- Selected-medium source: {selected_content_source}
- Selected-medium result: {selected_content_result}
- Cross-medium fallback source: {fallback_content_source}
- Cross-medium fallback result: {fallback_content_result}
- Selected item IDs:
- Exact focus: {content_need_text}
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `selected-output` (configured source library)
- Result: `SKIP` unless continuity was requested
- Selected item IDs:
- Usable evidence:
"""
    atomic_write_text(task_dir / "evidence-log.md", evidence)
    prompt = compile_prompt(brief, {"schema_version": 1, "references": []})
    atomic_write_text(task_dir / "prompt.md", prompt)
    (task_dir / "attempts").mkdir()
    atomic_write_text(task_dir / "preference-events.jsonl", "")
    atomic_write_json(
        task_dir / "response-window.json",
        {
            "schema_version": LATENCY_SCHEMA_VERSION,
            "started_at": created_at,
            "pre_generation_started_at": created_at,
            "pre_generation_target_seconds": pre_generation_target,
            "post_generation_target_seconds": args.post_generation_target_seconds,
            "generation_latency_policy": "observe-only",
            "phase": "pre-generation",
        },
    )
    print(task_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
