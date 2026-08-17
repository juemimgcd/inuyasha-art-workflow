#!/usr/bin/env python3
"""Create a non-destructive art task workspace with evidence and QA records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from task_workflow import (
    BRIEF_SCHEMA_VERSION,
    CHANGE_CATEGORIES,
    CHANGE_SCOPE_SCHEMA_VERSION,
    CHANGE_SCOPES,
    DEFAULT_EDIT_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_MAX_TECHNICAL_RETRIES,
    DEFAULT_NEW_PRE_GENERATION_TARGET_SECONDS,
    DEFAULT_POST_GENERATION_TARGET_SECONDS,
    INTENT_VALUES,
    LATENCY_SCHEMA_VERSION,
    QA_DIMENSIONS,
    QA_SCHEMA_VERSION,
    SCOPED_STYLE_CHANGE_CATEGORIES,
    compile_prompt,
    identity_requirements,
    new_split_domain_reference_strategy,
    read_json,
)
from workflow_common import (
    FORM_VALUES,
    SHOT_VALUES,
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
    medium: str,
    intent: str = "new",
    change_category: str | None = None,
    change_scope: str | None = None,
    shot: str | None = None,
    prop_forms: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    source_check = (
        "若使用漫画风格截图，它只控制画法，没有复制其人物、文字、分镜或剧情"
        if medium == "manga"
        else "若使用 TV 截图，它只控制配色与动画画法，没有复制其构图、人物或剧情"
    )
    medium_specific_checks = (
        [
            (
                "medium",
                "整体处于所选风格参考与镜头功能对应的完成度区间：局部细节较多但仍保持原作式线条、网点、黑白块和视觉主次时记为 warning；只有发丝、碎衣褶、微纹理、平滑体积光或均匀数字轮廓把第一印象推成精修黑白插画时才 fail；通用动漫脸、空洞场景、缺少结构关系或身份关键眼型、刘海、下颌、发型轮廓、服装层次和接触关系同样 fail",
            ),
            (
                "medium",
                "角色轮廓粗细、脸部简化、头发分束与布料衣褶使用所选 origin-photos 风格参考的笔触逻辑，同时没有复制参考图中的人物身份、姿势或构图",
            ),
            (
                "medium",
                "逐个人物检查可见的脸、头发、服装和手部：身份结构来自 official，轮廓节奏、用线密度、布料与衣褶概括来自所选人物画风素材；同人物同形态素材只是优先项，使用兼容素材时不得改写人物五官、发型轮廓、形态或服装",
            ),
            (
                "medium",
                "逐项检查画面中实际可见的场景材质、天气与光影现象：雨线、反光、阴影和材质细节可为叙事服务；局部略密但仍使用原作式选择性用线、留白、黑白块和远近衰减时记 warning，只有平滑写实塑形、电影式照明或全画面同等精度造成媒介偏移时才 fail；不可见项目记为 n/a 并说明原因",
            ),
            (
                "medium",
                "official 规定的服装部件、层叠、纹样和附件保持不变；这些部件之间的纸白、整块黑与克制中间网点深浅关系来自所选 origin-photos 风格参考且层级清楚",
            ),
        ]
        if medium == "manga"
        else []
    )
    medium_edit_checks = (
        [
            (
                "medium",
                "媒介修改把画面移入所选风格参考的场景完成度区间，而不只是去掉灰阶或换成网点；多余精修被削弱，但身份关键脸型、刘海、发型轮廓、服装结构、手部接触与必要场景线索没有被删成通用简陋线稿",
            )
        ]
        if medium == "manga" and change_category == "medium"
        else []
    )
    scoped_style_checks = []
    if medium == "manga" and change_category in SCOPED_STYLE_CHANGE_CATEGORIES:
        if change_scope == "character":
            scoped_style_checks = [
                (
                    "medium",
                    "人物域修改只使用 character-style：服装纸白、整块黑和网点值阶及人物线条可按人物漫画原图调整；场景材质、水体、岩石、植被、天气、背景密度和构图保持目标图不变",
                )
            ]
        elif change_scope == "scene":
            scoped_style_checks = [
                (
                    "preservation",
                    "场景域修改只使用 scene-style：人物脸、头发、服装部件、衣褶画法以及既有服装纸白、整块黑和网点值阶保持目标图不变，不得因水体或背景简化而重新上色",
                )
            ]
    wide_scene_checks = (
        [
            (
                "medium",
                "远景先保留场景中连续可见的纸白开阔面，再以少数整块黑、中间调和轮廓组组织建筑、植被、地形，并让每一层远景明显减少内部线条；只有单一从属区域略密且缩略图仍由大块纸白、黑和中间调主导时才记 warning；若多个材质或远近层同时铺满微纹理、距离不减线，或第一眼成为版画、蚀刻或精修黑白插画，即使物件齐全和透视正确也必须 fail，不能记 warning",
            ),
            (
                "composition",
                "远景的主要轴线、遮挡、尺度、路线和接地关系连续，未绘区域也是清楚的构图决定",
            ),
        ]
        if medium == "manga" and shot == "wide-shot"
        else []
    )
    character_finish_checks = (
        [
            (
                "medium",
                "人物中近景优先检查脸、眼睛、头发和衣褶的媒介偏移：少量局部线条略密但仍符合原作人物画法时记 warning；平滑体积塑形、跨区域均匀光泽、发丝级均匀刻画或现代精致插画式五官时才 fail",
            )
        ]
        if medium == "manga"
        and shot in {"face", "profile", "close-up", "medium-shot", "upper-body", "two-shot"}
        else []
    )
    prop_checks = []
    for prop, form in (prop_forms or {}).items():
        construction = [
            value
            for value in identity_requirements(prop, form)
            if value.startswith(("连续结构：", "明确数量："))
        ]
        prop_checks.append(
            (
                "identity",
                f"{prop} 使用官方 {form} 形态，风格与动作参考不改变其规范轮廓",
            )
        )
        if construction:
            prop_checks.append(
                (
                    "construction",
                    f"{prop} 的" + "；".join(construction),
                )
            )
    wide_edit_preservation_checks = (
        [
            (
                "preservation",
                "远景编辑保持目标图的取景、镜头距离、人物尺度与位置、主要物件、透视轴线和整体黑白分配；除非请求明确点名，否则不得靠放大人物、重新裁切构图、增加大块重黑或强化戏剧性来表现漫画感",
            ),
            (
                "medium",
                "远景编辑没有把简练误解为全画面均匀变空，而是在原构图内通过线条粗细与断续、局部笔触聚类、选择性细节和距离衰减修正画法",
            ),
        ]
        if medium == "manga" and intent == "edit" and shot == "wide-shot"
        else []
    )
    full = [
        *BASE_QA_ITEMS[:-1],
        *medium_specific_checks,
        *medium_edit_checks,
        *scoped_style_checks,
        *wide_scene_checks,
        *character_finish_checks,
        *prop_checks,
        *wide_edit_preservation_checks,
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
        (
            "preservation",
            "目标区域以外的人物、构图、画法和背景保持不变；没有额外数字精修，也没有删掉身份关键线条或必要场景线索",
        ),
        ("identity", "局部编辑没有造成角色身份、形态或服装漂移"),
    ]
    if category in {"construction", "costume", "anatomy", "composition"}:
        checks.append(
            (
                "construction",
                "修改区域的连接、遮挡、透视和接地关系连续，没有悬浮或穿模",
            )
        )
    if medium == "manga":
        checks.append(
            (
                "preservation",
                "局部修改没有增加细碎发丝、衣褶、微纹理、平滑阴影或数字精修感",
            )
        )
    return [
        *checks,
        *scoped_style_checks,
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
    parser.add_argument("--change-scope", choices=CHANGE_SCOPES)
    parser.add_argument("--change-request")
    parser.add_argument("--aspect-ratio", default="2:3 portrait")
    parser.add_argument("--shot", choices=SHOT_VALUES)
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
        "--prop-form",
        type=parse_identity_form,
        action="append",
        default=[],
        metavar="PROP=FORM",
        help="Declare the exact canonical form of a named weapon or prop.",
    )
    parser.add_argument(
        "--scene-material",
        action="append",
        default=[],
        metavar="VISIBLE_MATERIAL",
        help="Name scene-material scope that inherits the primary style anchor's economy.",
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
        "--content-kind",
        choices=("content", "scene"),
        default="content",
        help="Use scene for selected-medium canonical-place evidence.",
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
    if args.change_scope and not args.change_category:
        raise SystemExit("--change-scope requires --change-category")
    if intent == "new" and args.change_scope:
        raise SystemExit("--change-scope is only valid for edit or microfix")
    if (
        intent in {"edit", "microfix"}
        and args.change_category in SCOPED_STYLE_CHANGE_CATEGORIES
        and not args.change_scope
    ):
        raise SystemExit(
            f"{args.change_category} changes require --change-scope character|scene"
        )
    if parent_brief and parent_brief.get("medium") != args.medium:
        raise SystemExit("Parent and child tasks must use the same medium")
    content_query = args.content_query.strip()
    content_focus = args.content_focus.strip()
    if bool(content_query) != bool(content_focus):
        raise SystemExit("--content-query and --content-focus must be supplied together")
    if not content_query and args.content_provenance != "observed-content":
        raise SystemExit("--content-provenance requires a planned content query")
    period_mode = (
        args.period_mode
        or (parent_brief or {}).get("period_mode")
        or ("classic-balanced" if args.medium == "manga" else None)
    )
    shot = (parent_brief or {}).get("shot") or args.shot
    if parent_brief and args.shot and args.shot != shot:
        raise SystemExit("A continuation cannot silently change the parent shot")
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
    inherited_prop_forms = (parent_brief or {}).get("prop_forms") or {}
    supplied_prop_forms = dict(args.prop_form)
    if len(supplied_prop_forms) != len(args.prop_form):
        raise SystemExit("Each prop may have only one --prop-form")
    prop_forms = supplied_prop_forms or dict(inherited_prop_forms)
    if parent_brief and supplied_prop_forms and prop_forms != inherited_prop_forms:
        raise SystemExit("A continuation cannot silently change parent prop forms")
    if set(identity_forms) & set(prop_forms):
        raise SystemExit("A subject cannot be declared as both a character and a prop")
    inherited_materials = list(
        (parent_brief or {}).get("dominant_scene_materials") or []
    )
    dominant_scene_materials = list(
        dict.fromkeys(
            value.strip()
            for value in (args.scene_material or inherited_materials)
            if value.strip()
        )
    )
    inherited_invariants = list((parent_brief or {}).get("invariants") or [])
    supplied_content_need = (
        {
            "query": content_query,
            "focus": content_focus,
            "kind": args.content_kind,
            "selected_medium_source": (
                "manga-curated" if args.medium == "manga" else "tv-curated"
            ),
            "fallback_source": (
                None
                if args.content_kind == "scene"
                else ("tv-curated" if args.medium == "manga" else "manga-curated")
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
        "change_scope_schema_version": (
            CHANGE_SCOPE_SCHEMA_VERSION
            if intent in {"edit", "microfix"}
            else None
        ),
        "change_scope": args.change_scope,
        "change_request": args.change_request or "",
        "medium": args.medium,
        "deliverable": args.deliverable,
        "period_mode": period_mode,
        "style_strategy": f"two-layer-{args.medium}-fast",
        "reference_strategy": (
            new_split_domain_reference_strategy() if intent == "new" else None
        ),
        "style_references": [],
        "content_need": content_need,
        "content_references": [],
        "characters": list(identity_forms),
        "identity_forms": identity_forms,
        "character_style_targets": identity_forms if intent == "new" else {},
        "props": list(prop_forms),
        "prop_forms": prop_forms,
        "forms_and_costumes": [
            f"{character}: {form}" for character, form in identity_forms.items()
        ],
        "scene": (parent_brief or {}).get("scene", ""),
        "dominant_scene_materials": dominant_scene_materials,
        "shot": shot,
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
            "schema_version": QA_SCHEMA_VERSION,
            "status_values": ["pending", "pass", "warning", "fail", "n/a"],
            "dimensions": [
                {"id": dimension_id, "label": label, "status": "pending", "note": ""}
                for dimension_id, label in QA_DIMENSIONS
            ],
            "checks": [
                {"category": category, "check": check, "status": "pending", "note": ""}
                for category, check in qa_items(
                    args.medium,
                    intent,
                    args.change_category,
                    args.change_scope,
                    shot,
                    prop_forms,
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
- Change scope: `{args.change_scope or 'target-only'}`
- Requested change: {args.change_request}
- Additional source: `N/A` unless a new detail reference is prepared.
- Result: `HIT` from target continuity; inspect any added reference before generation.
"""
    else:
        selected_content_source = (
            "manga-curated" if args.medium == "manga" else "tv-curated"
        )
        fallback_content_source = content_need.get("fallback_source") or "ImageGen"
        content_need_text = content_need.get("focus") or "N/A"
        content_query_text = content_need.get("query") or "N/A"
        canonical_scene_planned = content_need.get("kind") == "scene"
        ordinary_content_planned = bool(content_need) and not canonical_scene_planned
        selected_content_result = "" if ordinary_content_planned else "SKIP"
        fallback_content_result = "" if ordinary_content_planned else "SKIP"
        scene_identity_result = "" if canonical_scene_planned else "SKIP"
        scene_style_coverage = "" if canonical_scene_planned else "SKIP"
        scene_style_coverage_basis = "" if canonical_scene_planned else "N/A"
        character_style_preference_lines = "\n".join(
            f"- Character style preference {character}={form}: exact / compatible / general"
            for character, form in identity_forms.items()
        )
        evidence = f"""# Evidence log

Task: `{task_id}`
Intent: `{intent}`
Change category: `{args.change_category or 'N/A'}`
Change scope: `{args.change_scope or 'target-only'}`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, `INSUFFICIENT`, or `SKIP` before advancing: official identity -> character rendering -> scene identity or construction -> scene rendering -> optional exact content -> optional continuity. Canonical scenes search the selected-medium scene domain first. When scene identity is `HIT`, separately record `Scene style coverage: HIT|INSUFFICIENT`; only `HIT` may skip Layer 4. On identity `MISS`/`INSUFFICIENT`, ImageGen constructs the scene and Layer 4 becomes mandatory. Actions, expressions, and complex staging are always generated, never retrieved as authority.

## Layer 1: official identity

- Need:
- Source searched:
- Result:
- Selected item IDs:
- Usable evidence:

## Layer 2: character rendering

- Need:
- Source browsed:
- Selected item IDs:
- Result:
- Character mark-making coverage:
- Hair and face linework coverage:
- Fabric and fold treatment coverage:
- Garment value hierarchy coverage:
{character_style_preference_lines}
- Must not control: action, pose, expression, interaction, framing, or scene
- Controls: character linework, face/hair simplification, costume mark-making and value hierarchy only

## Layer 3: scene identity or construction

- Need: {content_need_text if content_need.get('kind') == 'scene' else 'scene described by request'}
- Scene-domain query: {content_query_text if content_need.get('kind') == 'scene' else 'generic scene facets'}
- Scene identity result: {scene_identity_result}
- Selected item IDs:
- Scene style coverage: {scene_style_coverage}
- Coverage basis: {scene_style_coverage_basis}
- Fallback after MISS/INSUFFICIENT: ImageGen constructs the scene

## Layer 4: scene rendering

- Source browsed: selected-medium `reference_domain=scene`
- Scene style result:
- Selected item IDs:
- Allowed SKIP: only when Layer 3 scene identity is HIT and Scene style coverage is HIT
- Scene rendering coverage:
- Dominant material rendering coverage: transfer one scene anchor's information budget across the listed scene scope; do not add one reference per material
- Controls:
- Must not control: characters, pose, action, expression, interaction, or framing

## Layer 5: exact content evidence

- Need: {content_need_text}
- Query: {content_query_text}
- Selected-medium source: {selected_content_source}
- Selected-medium result: {selected_content_result}
- Cross-medium fallback source: {fallback_content_source}
- Cross-medium fallback result: {fallback_content_result}
- Selected item IDs:
- Exact focus: {content_need_text}
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 6: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
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
