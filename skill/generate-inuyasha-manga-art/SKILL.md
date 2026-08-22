---
name: generate-inuyasha-manga-art
description: "Generate, edit, microfix, or art-direct character-accurate Inuyasha manga or TV images with official identity sheets, selected-medium originals, accepted-output continuity, intent-aware prompts, append-only attempt feedback, and validated reference manifests. Use for 犬夜叉角色、漫画版、原著漫画风格、TV版、动画版画风、设定集、角色立绘、漫画插图、漫画分镜、动画场景、战斗、妖怪、连续性修图、局部修图、reference manifests, prompt refinement, or image-workflow maintenance."
---

# Generate Inuyasha art

## Keep authority separate

- Official setting sheets control identity, form, anatomy, costume, weapon,
  prop, attachment, and scale, including canonical garment components, layering,
  patterns, and accessories. They do not decide how those parts are inked or
  divided into paper-white, flat-black, and halftone values.
- Character rendering comes only from selected-medium originals in
  `origin-photos`, hard-filtered to `reference_domain=character-style`. It must
  also depict a requested focal character in that character's exact requested
  form, with no unrequested known character in the panel. If that eligible set
  is empty or visibly insufficient, record `MISS` or `INSUFFICIENT`; never
  substitute another character or form automatically. It
  controls contour rhythm, face and hair linework, fabric/fold treatment and
  garment value hierarchy; action, expression, interaction and scene terms do
  not participate in its ranking. A separately persisted `view_angle` does
  participate because face, bangs, jaw, and hair mark-making must be applicable
  to the requested direction; it never grants pose or composition authority.
- Scene evidence comes only from `origin-photos/.../场景`, indexed as
  `reference_domain=scene`. Search an exact `scene-id` first for work-specific
  places such as 食骨之井 or 御神木. A canonical-scene `HIT` must separately
  record `scene_style_coverage=HIT|INSUFFICIENT` plus a concrete visible
  inspection basis; evidence, brief, and manifest must agree. Only `HIT` lets
  the same input control scene rendering. On identity `MISS`/`INSUFFICIENT`, or style coverage
  `INSUFFICIENT`, ImageGen constructs the needed staging and a separate
  scene-domain image controls materials, weather, negative space, black-white
  mass and detail falloff.
- A separately planned curated `content` image may control only one exact visible
  action, object, creature, effect phase, or spatial fact.
- A `selected-output` controls accepted continuity only when continuity is asked for.
- The user target controls the exact instance and every unchanged region of an edit.
- The request and ImageGen control the new staging, pose, action, expression,
  interaction, camera and any non-canonical scene construction.

Never select a style image by a fixed volume, page, episode, or file. Retrieve it
from the current scene need. Never let it control identity or copy its characters,
costume construction, dialogue, layout, pose, or story. Never let cross-medium
content control style or identity.

## Load only the required contract

This file is the complete standard contract for a first preview. Read
`references/workflow-contract.md` completely only for workflow maintenance,
cross-medium fallback, migration/archive, final acceptance, or a validation
failure whose cause is unclear. For an ordinary `new`, `edit`, or `microfix`
preview, do not load the full contract or `quality-gate.md` before generation.

Use the bundled launcher. From a repository checkout on macOS/Linux:

```bash
skill/generate-inuyasha-manga-art/scripts/run-python \
  skill/generate-inuyasha-manga-art/scripts/<script>.py <args>
```

If the launcher reports that Pillow is unavailable, do not install into system,
Homebrew, Codex-bundled, or another project's Python. In the package checkout,
run `./setup-python-env.sh` to create its ignored `.venv`; in a temporary
worktree, set `INUYASHA_PYTHON` for that command to an existing project `.venv`.
Package-maintenance validation must use `requirements-dev.txt`, which adds
PyYAML to the same repository-only environment.

From PowerShell after running `setup-windows.ps1`:

```powershell
& "$HOME\.agents\skills\generate-inuyasha-manga-art\scripts\run-python.ps1" `
  "$HOME\.agents\skills\generate-inuyasha-manga-art\scripts\<script>.py" <args>
```

Check catalog freshness before retrieval and rebuild only when stale:

```bash
scripts/run-python scripts/build_reference_index.py --check
scripts/run-python scripts/build_reference_index.py
```

On PowerShell, substitute `scripts/run-python.ps1` and invoke it with `&`.
The setup script defines `INUYASHA_WORKFLOW_HOME`; `INUYASHA_WORKFLOW_ROOT`
may override only the generated workflow-data directory. Do not rewrite
historical task paths when moving machines—the compatibility resolver maps them.

## Minimize controllable preview overhead

Measure three phases separately: controllable pre-generation work, external
image-generation latency, and controllable post-generation work. Generation
latency is observation-only: never skip evidence, block a valid generation, or
stop a meaningful retry merely because a total-response clock is running out.

Use soft targets, not deadlines: 30 seconds before generation for `edit` and
`microfix`, 90 seconds for `new`, and 30 seconds after generation. A task may
override them. Start phase tracking inside the first batched local execution:

```bash
scripts/run-python scripts/start_response_window.py --task-dir <task-directory>
```

Before the image call, snapshot the exact submitted prompt and every ordered
input file. This rejects an untracked target under a `new` task and makes payload
size, transport, and real edit intent auditable:

```bash
scripts/run-python scripts/prepare_generation_submission.py \
  --task-dir <task-directory>
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage pre-generation
```

Immediately before the image call, mark the phase transition in the same
execution boundary that launches generation. Schema-5 tasks cannot enter the
generation phase without the prepared submission snapshot:

```bash
scripts/run-python scripts/start_response_window.py \
  --task-dir <task-directory> --mark-generation-started
```

Optimize only work the agent controls:

- Target-only first edit preview: inspect the target, create only the lightweight
  tracked edit record, snapshot the target submission, make one image call, then
  perform one blocking check and immediate handoff. Do not locate a historical
  parent, search references, prepare a proxy, or run non-blocking QA unless
  continuity, additional authority, or fragile transport requires it.
- Tracked edit: at most three execution boundaries — one batched local
  preparation, one image call, one blocking check plus save/record/handoff.
- Standard new image: at most four boundaries — one serial candidate inspection,
  one batched prepare/compile/validate step, one image call, one blocking check.
- Make one generation call and show the first usable preview. Do not silently
  generate alternatives or aesthetic polish.
- Batch task updates, attempt recording, reference preparation, prompt compilation,
  and pre-generation validation when their inputs are already known.
- Candidate previews require one direct check for identity/form, requested edit
  scope, medium density band when applicable, and technical integrity. Inspect the image already returned by the image
  tool; call `view_image` only when that result is not visually available. Do not
  fill all of `qa.json`, re-read the quality gate, or run final validation before
  user acceptance.
- When `medium` is the named change, its direct check is blocking. Reject a manga
  candidate that merely removes gray or adds screen tone while retaining polished
  contours, dense strands, folds, patterns, textures, or background rendering.
  Also reject a generic sparse anime/coloring-book result that lost identity
  anchors, garment construction, contact, or required setting cues.
- `record_attempt.py --status candidate` is a hard handoff gate: supply exactly
  one `identity`, `request`, `medium`, and `technical` preview check. Identity,
  request, and technical must be `pass`; medium may be `warning` when the image
  remains visibly inside the selected manga language and only a localized,
  non-dominant density drift remains. Every result needs a concrete visual
  evidence note. A missing, duplicate, unknown, note-free, misplaced warning,
  or failed check blocks the
  candidate before it is persisted or reported as handoff-ready. Record a visual
  failure as `rejected` with a structured failure instead of weakening this gate.
- A current manga candidate with selected style authority, including scoped
  `edit` and `microfix` tasks, must also record four
  concrete `--medium-component-check` rows: `face-hair`, `fabric-fold`,
  `scene-material`, and `value-hierarchy`. Use `pass`, `warning`, or `fail` for a
  visible component and evidence-backed `n/a` when it is genuinely outside the frame;
  value hierarchy is always applicable and must be `pass` for a candidate. When
  the overall medium check is `warning`, exactly one of the other component rows
  must carry the identical normalized evidence note for the same localized
  warning; multiple component warnings or a
  component warning under `medium=pass` block handoff. These rows check stable character,
  scene, and value authority boundaries rather than a fixed defect blacklist.
  A wide shot may mark unreadable character components `n/a`, but it still
  checks scene rendering and value hierarchy.
- A candidate with any critical failure is ineligible to win a visual A/B case.
  When both sides have critical failures, record a tie/both-fail instead of
  promoting the relatively less bad image. Explicit later user feedback is
  append-only and supersedes an earlier promotion without rewriting its blind
  judgment or immutable result.
- After a usable output, combine copying to the workspace, attempt recording, and
  any required preview metadata in one local execution. Hand off immediately;
  aesthetic alternatives and final QA wait for user feedback.
- A first technical failure may be retried only when the input, wording, or
  transport condition changes. Retry limits depend on consecutive technical
  failures, never on elapsed generation time.
- A network failure lasting at least 180 seconds is treated as having exhausted
  the image client's internal transport retries. Do not start an outer retry,
  even in a new response window. Only a later explicit user request may authorize
  one call with `start_response_window.py --authorize-network-retry
  --authorization-note <exact-user-request>`.
- After an image-call failure, record an `error` attempt with
  `technical=NOTE` before commentary or retry. This closes the response window
  and preserves the failure even if the next user message interrupts the turn.
- Pass generation wall time as `--duration-seconds` to `record_attempt.py`. It
  records generation latency separately from pre- and post-generation overhead.

The local catalog check, search, prompt compilation, and validation should remain
sub-second. Use `reference_feedback_report.py` to report generation latency and
controllable pre/post overhead separately by intent.

For retrieval maintenance, run the inspected Top-K benchmark after changing
intent aliases, annotations, ranking weights, or catalog metadata:

```bash
scripts/run-python scripts/benchmark_reference_retrieval.py --check --json
```

Identity-card collages are retired from generation inputs. Keep their manifests,
recipes, images, attempts, and completed benchmark runs only as historical
provenance. Do not rebuild, select, upload, or prepare a new benchmark run from
them. A future backend comparison must use a new immutable dataset whose identity
inputs are shot-matched official setting sheets or focused official crops.

For workflow changes that can affect generated-image quality, use a lightweight
three-case blind A/B gate. Use `references/visual-eval-v2.json` for `new` paths
and `references/visual-edit-eval-v1.json` for target-only or scoped `edit` paths;
never use an all-`new` dataset to claim an edit-only improvement. Generate exactly
one baseline and one candidate image for each case: three images per workflow,
six total. Use the same backend for the whole run. Each dedicated evaluation task
must contain exactly one recorded generation attempt at `attempts/001`; never
retry, add a second attempt, or replace a slot. Judge the A/B pairs before opening
`blind/blind-key.json`. The candidate may replace the baseline only when it wins
at least two cases and has no critical identity, medium, request,
anatomy/contact, or technical failure.

When the revision changes manga anchor ranking, rendering-map compilation, or
generator-facing character/scene finish calibration, use the focused gates
instead: `references/visual-manga-style-eval-v1.json` for `new` and
`references/visual-manga-style-edit-eval-v1.json` for scoped `edit`. A revision
that changes both paths must pass both focused datasets before it is described as
visually promoted. These focused cases compare face/hair grouping, fabric/fold
economy, value hierarchy, paper-white, scene grouping, and depth falloff; they do
not replace identity, request, anatomy/contact, or technical critical checks.

A revision limited to post-generation candidate eligibility, comparison-sidecar
validation, warning consistency, attempt persistence, or lifecycle auditing does
not change generator inputs or output pixels. Validate it with deterministic
candidate-gate regression cases covering current `new`, scoped `edit`, valid
controls, each rejected boundary, and failure-before-mutation behavior. Such a
revision may be described only as handoff-selection or audit hardening, never as
raw generated-image quality or visual promotion. If the same revision also
changes a prompt, reference input, ranking, or rendering map, the relevant visual
A/B gates remain mandatory.

```bash
scripts/run-python scripts/visual_ab_eval.py --check --json
scripts/run-python scripts/visual_ab_eval.py --check --json \
  --dataset references/visual-edit-eval-v1.json
scripts/run-python scripts/visual_ab_eval.py --check --json \
  --dataset references/visual-manga-style-eval-v1.json
scripts/run-python scripts/visual_ab_eval.py --check --json \
  --dataset references/visual-manga-style-edit-eval-v1.json
scripts/run-python scripts/visual_ab_eval.py --prepare \
  --dataset references/visual-edit-eval-v1.json \
  --run-id <run-id> --baseline-label <old-revision> \
  --candidate-label <new-revision> --backend <same-backend>
```

Immediately after each image call, use `record_attempt.py` with the truthful
`candidate`, `rejected`, or `error` status and `--generator <same-backend>` so
attempt 001 snapshots the exact brief, compiled and submitted prompts, manifest,
output hash when present, backend, and generation time. Bind it to the gate with:

```bash
scripts/run-python scripts/visual_ab_eval.py --record \
  --run-dir <run-directory> --variant <baseline-or-candidate> \
  --case-id <case-id> --task-dir <dedicated-task-directory> \
  --attempt-dir <dedicated-task-directory>/attempts/001
```

Every baseline/candidate pair must use byte-identical ordered inputs; the gate
checks role, item ID, order, and SHA-256 before blinding. An `error` attempt is
locked as the one consumed slot, including its inputs and telemetry, but it has
no visual output and therefore blocks blinding without permitting a retry. After
all six visual slots are locked, use `--blind`, one immutable `--judge` call per
case, and `--results --json`. Run, slot, prompt, input, output, blind image,
mapping, and judgment hashes are rechecked before a verdict is written. Do not
treat unit tests, retrieval metrics, prompt inspection, or an unscored generation
as proof that the candidate improved visual quality.

If later explicit user feedback identifies a critical defect that the blind
review missed, preserve the original result and append the correction with
`visual_ab_eval.py --record-human-feedback --feedback-failure
CASE_ID=VARIANT:CATEGORY --note ...`. Read the current decision with
`--effective-results`; never rewrite the original judgment or `results/result.json`.
Before activating, packaging, or describing a generation-quality-affecting
revision as the new workflow, run `visual_ab_eval.py --assert-promoted
--run-dir <run-directory>`.
This command uses the feedback-aware effective verdict and exits nonzero for an
incomplete run, `keep_baseline`, or any later candidate critical failure.
For one combined release check, run `validate_workflow.py --visual-run-dir
<run-directory> --require-visual-promotion`. Plain `validate_workflow.py` now
reports `validation_scope: structural-only` and explicitly warns that `ok=true`
does not prove generated-image quality.

## Route by intent

- `new`: create a new composition. Start with one inspected, shot-matched official
  setting sheet or focused official crop per focal character, plus one
  selected-medium style image.
- `edit`: preserve a supplied target. Start target-only when it already provides
  the unchanged identity and medium; otherwise add only the single authority role
  required by the named change. Every `medium` or `tone` edit must declare
  `change_scope=character|scene`; never use one scene-style reference to retone
  character clothing or one character-style reference to redraw the environment.
- `microfix`: continue an accepted parent task, inherit validated evidence, and
  reopen only one change category. Use crop-and-composite for a bounded region.

Default ambiguous medium requests to `manga`. Use `tv` only when explicitly asked.

For manga, use the corpus-derived density band in `references/style-guide.md`:
direct late-1990s serialized-page drawing whose information density follows the
shot and narrative focus. Reject both polished prestige line art and generic,
under-rendered coloring-book linework. Economy means preserving the right marks,
especially identity-bearing eyes, bangs, jaw, hair silhouette, costume layers,
hands, contact, and necessary setting cues. Treat the guide as offline
calibration, not as an instruction to retrieve a fixed source volume or page.
Choose one dynamic style image for every new image and named medium replacement.
Never turn the guide into numeric caps or percentage reductions for strands,
folds, tones, rain lines, or background marks.

Judge finish drift by severity rather than raw detail count. Use `pass` when the
shot's detail distribution and medium both match, `warning` when localized extra
detail remains subordinate to the original manga line/tone/black-white hierarchy,
and `fail` only when refinement becomes globally dominant or changes the first
impression into prestige line art, smooth volume rendering, cinematic lighting,
or another medium. A warning never excuses identity, request, construction, or
technical defects.

For a manga `wide-shot`, rely on the dedicated scene-economy branch compiled
from the persisted shot. Preserve spatial structure through silhouette, major
axes, overlap, scale, route, and ground contact while deliberately omitting
repeated surface detail. Large white paper, flat black masses, clustered
forms, and distance-based detail falloff are required authoring decisions.
Reserve contiguous open scene shapes as untouched paper before secondary marks,
group repeated materials into a few value families, and visibly reduce internal
marks at every successive depth layer. Treat only one subordinate local density
drift as warning territory; multi-material or multi-depth uniform microtexture is
a medium failure regardless of object completeness or correct perspective.
Retrieve them through the positive observable traits
`scene-economy:authored-negative-space` and `detail-falloff:strong`. Use one
primary rendering anchor and transfer its information budget across the whole
scene; scene materials do not create separate reference slots.

For a manga `wide-shot` edit, lock the supplied target's framing, crop, camera
distance, character scale and placement, major object positions, perspective
axes, and overall black-white distribution unless the request explicitly names
one of them as the change. Do not answer “still not manga-like enough” by
enlarging the character, recomposing the scene, adding large new black areas, or
making the staging more dramatic. Also do not simplify the whole canvas
uniformly. Keep the approved wide-shot balance and refine only local
mark-making: contour taper and breaks, clustered marks, selective density, and
distance falloff. When the user says an earlier candidate is closer, use that
candidate as the target and reopen only the stated failure category.

## Fast new-image path

Initialize the task and retrieve at most four exact candidates per layer. Only
official setting sheets assigned to an explicitly curated similar-content series
share one candidate slot; choose that series' representative from the current
request, and keep the full catalog available for explicit inspection:

```bash
scripts/run-python scripts/plan_art_task.py \
  --slug inuyasha-forest-strike \
  --request "犬夜叉在森林中挥出铁碎牙" \
  --identity-form 犬夜叉=half-demon-form \
  --prop-form 铁碎牙=transformed-form \
  --shot action
```

Store camera distance and character direction separately. For example, an
upper-body profile uses `--shot upper-body --view-angle profile`. The planner
may infer one unambiguous explicit direction such as `侧脸` or `侧身`, but a
conflicting or multi-direction request must be split or declared explicitly.

Inspect the planner's official identity candidates for every focal character.
Choose the single source whose view and visible construction best match the shot;
when the needed face, garment overlap, weapon mount, hand, or footwear occupies
only a small part of a sheet, prepare the smallest focused task-local crop and
record its source hash, crop box, rendered hash, and focus. Then inspect the
character-style domain. Never filter it to a predetermined volume or page.
For schema-5 `new` tasks using `face`, `profile`, `close-up`, or `medium-shot`,
pre-generation validation blocks an uncropped official setting sheet when its
shot facets do not match the requested view. Use `prepare_reference_set.py
--crop ITEM_ID=X,Y,W,H --focus ITEM_ID=...`; do not compensate with a manga
style image or an identity collage.
When `brief.view_angle` is present, official identity evidence must carry that
exact controlled view facet or be a focused task-local crop of the required
view. Character-style evidence must also visibly cover the same view angle.
Viewless fallbacks are crop candidates only and never count as view coverage.
An image-level view tag on a multi-character panel is ambiguous unless the
requested character is the only possible owner of that view; do not transfer a
co-character's profile tag to the focal character.
When the planner adds both `scene-economy:authored-negative-space` and
`detail-falloff:strong`, the selected scene-style reference must visibly carry
both positive tags. A weather- or architecture-matched scene without those
traits is not sufficient scene-style evidence, even if its subject matter is
more literal.
Treat focal character and exact form as eligibility, not score. Character-style
candidates must depict at least one requested focal character in the exact
requested form and must not contain any unrequested known character. Only then
rank view applicability, shot, character mark-making and value hierarchy; do not
score action, interaction, expression, camera or scene similarity. If no eligible
candidate covers the requested view, record `MISS` or `INSUFFICIENT` and curate
same-character, same-form evidence. Never broaden across character or form. Next
search the scene domain. Exact canonical places
use `scene-id`; generic places use scene/background/weather traits for rendering
only. ImageGen owns all actions and complex staging. For scene rendering, a
requested shot is a soft ranking signal rather than an eligibility filter.
Prefer an anchor that covers the requested scene family, materials or weather
plus the needed economy traits over one that matches only camera distance.
Controlled scene traits explicitly present in structured folders or filenames
participate in ranking; manual annotations remain for visual distinctions such
as authored negative space and detail falloff that a filename cannot prove.
Every named canonical weapon or prop must declare its exact form. The official
layer issues a separate exact-form prop search; attach a focused official prop
sheet when needed. A manga action/style image may control foreshortening and
mark-making but never the prop silhouette or construction.
When the identity ledger supplies a topology contract, preserve its counted
features and connected part sequence. Form aliases and topology remain ledger
data so planner, prompt, and QA share one mechanism without prop-specific code.
Do not search `selected-output` unless continuity was requested. Add a
content layer only when identity and style evidence cannot resolve an exact named
fact. Expand beyond four candidates only after recording `MISS` or
`INSUFFICIENT`; never broaden across character form.

After choosing references, fill `brief.scene`, `brief.invariants`, and the
serial evidence results. Character and scene rendering are separate coverage
lines. Inspect only the exact-character-form eligible set, then select one
scene-style anchor. Exact character-form is a character-style eligibility gate
while official evidence remains the sole identity authority. Use one
character-style anchor by default; add a second
only when inspection records that the first is insufficient for a visible
character-rendering relationship. An exact canonical scene hit may cover both its structure and scene rendering in one
input only after recording `--scene-style-coverage ITEM_ID=HIT` and a concrete
`Coverage basis` in the evidence log. Record
`INSUFFICIENT` and select one additional scene-style image otherwise. Never
reuse a scene-domain image as character-style evidence.
Optional scene-material labels describe where the anchor's information budget
must transfer, not additional evidence requirements. Pass a non-empty `--focus` for
each style image that states exactly which of those visible relationships it
controls. Prepare references, compile, and validate in one local execution. A
normal single-character input is one character-style image, one scene-style
image, and one shot-matched official identity image or focused official crop. A
multi-character task may use a second complementary character-style image when
the first is visibly insufficient; it does not need one style image per person.
Hard maximum remains six.
Never add a retired identity-card collage.

Manually inspected `style-anchor:certified` items are only a same-score
tie-breaker. Their populated line-weight, tone-density, black-mass,
face-clarity, view-angle, depth-layout, scene-economy, and detail-falloff traits
make the choice inspectable, but certification never outranks a better
character/form/shot or scene/material match and never grants identity or content
authority. New manga briefs carry `rendering_map` schema 1. Review its positive
character grouping, focal/near/middle/far plane, paper-white, and value-hierarchy
relationships after filling scene and material scope; edit it when the request
needs a more exact mapping. The compiler turns it into concise prompt text and
validation checks its structure without rewriting historical briefs.
When exact object evidence contains a form-conflicting character outside the
needed region, use a focused task-local `content` crop only after visual
inspection proves the crop excludes that character. Never relax form checks for
the full image or for `identity`/`form` roles.

## Fast edit path

Place the target first. Use:

- target only for composition, background, polish, or any change already resolved
  by the target;
- target plus one official identity reference for identity, form, costume, or
  anatomy;
- target plus the smallest focused official crop for construction/contact;
- for a manga-medium correction, target plus one dynamically selected
  scope-matched manga style image; the bundled guide defines the allowed band but
  does not replace visual evidence;
- target plus at most one dynamically selected style image for any named medium,
  ink, tone, effect, or period treatment.

For `medium` and `tone`, declare exactly one rendering domain. `character`
selects `origin-photos` character-style evidence and controls face/hair/fabric/fold
mark-making plus garment value hierarchy. `scene` selects only
`origin-photos/.../场景` evidence and controls environmental materials, weather,
negative space, black-white mass and distance falloff. The other domain remains
locked to the target. If both domains need changes, make two bounded edits; do
not collapse them into one style input.

Current edit and microfix briefs persist `change_scope_schema_version: 1` so
both pre-generation and final validation can enforce this rule without rewriting
historical manifests. Legacy completed tasks with no explicit `style_scope`
remain readable and continuable by deriving their effective domain from the
catalog; an explicit wrong scope is never accepted. The schema marker must be
the JSON integer `1`; booleans, floats, and strings are invalid.

For a target-only first edit, batch task creation, target preparation, prompt
compilation, exact submission snapshot, and validation in one local command:

```bash
scripts/run-python scripts/prepare_quick_edit.py \
  --slug fix-right-hand \
  --request "只修正右手，其他内容保持不变" \
  --change-category anatomy \
  --target <target-image>
```

It returns a JSON object with `ready_for_generation: true`, the exact prompt, and
the tracked inputs. Add `--target-max-edge 960` only when a transport proxy is
actually needed; original target bytes are the default.

For a first preview that needs only the supplied target, do not create or search
for a historical task before generation. The target controls identity,
composition, spatial facts, and unchanged content; it does not control a medium
that the user asked to replace. For a manga-medium correction, simplify only the
declared domain where it exceeds the selected scope-matched density band.
Character scope may adjust strands, folds and garment values while preserving
the scene; scene scope may adjust environmental texture, shading and background
information while preserving every character mark and garment value. Preserve
identity anchors and structural invariants. Create or update the
durable task record only after a usable preview exists or when user feedback
makes continuity necessary. Technical failures without an output do not require
an empty replacement task.
For a target-only edit with no style input, the compiled prompt must say that no
external style authority is attached and preserve the target's existing character
and scene rendering. Never mention selected character or scene references that
are absent from the manifest.

For a fragile full-canvas upload, create a manifest-tracked proxy while retaining
the original path and hash:

```bash
scripts/run-python scripts/prepare_reference_set.py \
  --task-dir <task-directory> \
  --external target=<original-target> \
  --external-target-max-edge 960
scripts/run-python scripts/compile_prompt.py --task-dir <task-directory>
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage pre-generation
```

Use the manifest's rendered proxy path for generation. Do not create an untracked
JPEG. Skip the proxy when original-resolution line detail is required.

## Fast microfix path

Create a compact child task from an accepted result:

```bash
scripts/run-python scripts/continue_art_task.py \
  --from-task <accepted-task-directory> \
  --slug narrower-right-shoulder \
  --change-category anatomy \
  --change "只收窄犬夜叉右肩，其他区域保持不变"
```

For a style-bearing continuation, add `--change-scope character` or
`--change-scope scene`. The continuation resolves the nearest matching style
authority through the validated parent chain and must fail instead of taking the
first unrelated style row.

Domain isolation applies to the whole compiled prompt and QA, not only the main
edit sentence. A character-scoped edit must omit scene-material, scene-economy,
and global character-plus-scene calibration clauses. A scene-scoped edit must
lock character marks and garment values to the target. The same scoped
preservation row is required in both edit and microfix QA.

For a bounded local change, add `--edit-box X,Y,WIDTH,HEIGHT`. The script sends a
context crop; after generation, run `composite_local_microfix.py`. Final
validation must prove exact pixel preservation outside the edit box. Do not crop
when the change crosses the boundary or changes silhouette, composition,
perspective, or background globally.

When the source is a recorded but not-yet-accepted candidate, keep it unaccepted
and create a candidate-local `edit` task instead:

```bash
scripts/run-python scripts/continue_art_task.py \
  --from-task <task-with-recorded-candidate> \
  --from-attempt latest \
  --slug fix-candidate-hand \
  --change-category anatomy \
  --change "只修正犬夜叉藏在袖中的双手" \
  --edit-box X,Y,WIDTH,HEIGHT
```

`--from-attempt` requires a bounded edit box, verifies the immutable attempt
output hash, records that candidate as the first `target`, and reuses the same
crop-and-composite preservation gate. Prefer this route for hands, expressions,
sleeves, garment overlaps, and other bounded follow-up feedback. Use a tracked
full-canvas edit only when the requested change truly crosses the local boundary;
in that case pass `--full-canvas` instead of `--edit-box`.

## Attempts and acceptance

Submit compiled `prompt.md` verbatim by default; never append unrecorded
generator-only instructions. If a transport wrapper or deliberate prompt change
is unavoidable, save the exact submitted text and pass `--submitted-prompt`.
Record every candidate before another generation. Use `candidate` for a usable
preview awaiting user confirmation, `rejected` only for a failed visual result,
and `accepted` only after explicit approval. Rejections require a structured
failure; errors require `technical`; blame a reference only when it visibly caused
the defect:

For every manga candidate with a selected style input, first build and inspect
the reference-candidate sheet. It places the candidate beside each scoped style
authority and writes a hash-locked JSON sidecar; judge only the declared scope,
not the reference's identity, pose, text, or composition:

```bash
scripts/run-python scripts/image_sheet.py \
  --task-dir <task-directory> --candidate <candidate.png>
```

Keep the returned `comparison_sidecar` path; `record_attempt.py` verifies that
its candidate hash, ordered style rows, and sheet hash still match the actual
handoff inputs.

```bash
scripts/run-python scripts/record_attempt.py \
  --task-dir <task-directory> \
  --status candidate \
  --output <candidate.png> \
  --comparison-sidecar <candidate-manga-style-comparison.json> \
  --duration-seconds 75 \
  --persist-output \
  --preview-check identity="pass:face, form, costume, and marks match official evidence" \
  --preview-check request="pass:requested moment and action are visibly present" \
  --preview-check medium="pass:line, black, tone, and detail density match the selected medium" \
  --preview-check technical="pass:image is complete and artifact-free" \
  --medium-component-check face-hair="pass:visible character marks follow the selected character-style evidence" \
  --medium-component-check fabric-fold="n/a:no readable garment folds are inside this crop" \
  --medium-component-check scene-material="pass:visible setting marks follow the selected scene-style evidence" \
  --medium-component-check value-hierarchy="pass:black, white, and tone hierarchy matches the selected manga evidence" \
  --json
```

This single post-generation command persists the image, snapshots the exact
submission and comparison evidence, records the blocking preview checks, and returns a handoff-ready
output path. Do not run full QA or final validation before showing that preview.

For a modified submission add
`--submitted-prompt <exact-submitted-prompt.md>`. Each immutable attempt stores
brief and manifest snapshots, both compiled and submitted prompt hashes, plus
`submitted-prompt.md`.

After explicit user approval, complete the six QA dimensions and every applicable
detailed check first. Every current `new` task declares the structured
`reference_strategy.mode=split-domain`; compatibility tasks with QA schema 2 use
the same gate. `character_style` and `scene_style` may carry a documented
non-blocking `warning`; the other four dimensions must pass. A split-domain task
cannot be recorded as `accepted` while any dimension is pending or failed, or
while a warning appears outside the two style dimensions. Then record the
accepted attempt, read
the full workflow contract and quality gate, and run final validation:

```bash
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage final
```

For repository-wide audits, keep lifecycle meanings separate:
`validate_all_tasks.py --scope completed` checks accepted deliverables,
`--scope active` checks only prepared or candidate-pending work, and `--scope all`
is an intentional history inventory that may expose abandoned drafts and closed
failures. Do not report the history inventory as the health of current work.

Keep attempts append-only. Only repeated explicit feedback may update the stable
preference profile.

When the user accepts or rejects an already recorded candidate, append a decision
attempt pointing back to the candidate hash. It must set
`counts_as_generation: false`; the decision remains auditable without inflating
generation count, first-preview yield, or latency.

## Maintenance and deeper resources

Treat this installed skill as the live runtime. The checkout at
`/Users/jquery/Documents/inuyasha-art-workflow` is a packaging snapshot, not a
second writable runtime. Do not mirror maintenance changes into that checkout
unless the user explicitly asks to update the package. When packaging is
requested, use the checkout's `tools/sync_installed_skill.py` preview first and
name each file explicitly on apply; never overwrite its repository-specific
`references/source-library.json`. The tool must validate a staged copy of the
complete current package before mutation, create a unique backup manifest, and
roll back a partial write; never bypass it with a direct copy.

- `references/workflow-contract.md`: full schemas, lifecycle, compatibility,
  cross-medium, migration, and final-acceptance rules.
- `references/character-identity.md` and `identity-ledgers.json`: identity routing.
- `references/style-guide.md` and `tv-style-guide.md`: medium construction.
- `references/quality-gate.md`: full-size final QA.
- `references/visual-traits.md`: controlled retrieval annotation.

For maintenance, run `reference_feedback_report.py`, `validate_workflow.py`, and
the relevant task validation. The complete local manga PDFs are offline
calibration/evaluation material and a cold fallback after curated evidence is
recorded insufficient; do not attach whole volumes at runtime, upload them as
"training data", or claim model fine-tuning. Preserve original libraries and
historical attempts.
