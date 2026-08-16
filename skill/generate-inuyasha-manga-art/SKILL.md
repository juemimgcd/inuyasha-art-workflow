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
- The bundled medium guide supplies the offline calibration and QA band. Every
  `new` image and every named `medium` replacement uses one inspected,
  scene-matched selected-medium original from `origin-photos` for character
  contour rhythm, face and hair linework, fabric and fold treatment, garment
  value hierarchy, and scene rendering.
- A separately planned curated `content` image may control only one exact visible
  action, object, creature, effect phase, or spatial fact.
- A `selected-output` controls accepted continuity only when continuity is asked for.
- The user target controls the exact instance and every unchanged region of an edit.
- The request controls the new scene or named change.

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

For workflow changes that can affect generated-image quality, use the lightweight
three-case blind A/B gate in `references/visual-eval-v2.json`. Generate exactly
one baseline and one candidate image for each case: three images per workflow,
six total. Use the same backend for the whole run. Each dedicated evaluation task
must contain exactly one recorded generation attempt at `attempts/001`; never
retry, add a second attempt, or replace a slot. Judge the A/B pairs before opening
`blind/blind-key.json`. The candidate may replace the baseline only when it wins
at least two cases and has no critical identity, medium, request,
anatomy/contact, or technical failure.

```bash
scripts/run-python scripts/visual_ab_eval.py --check --json
scripts/run-python scripts/visual_ab_eval.py --prepare \
  --run-id <run-id> --baseline-label <old-revision> \
  --candidate-label <new-revision> --backend <same-backend>
```

Immediately after each image call, use `record_attempt.py` with `--status
candidate --generator <same-backend>` so attempt 001 snapshots the exact brief,
compiled and submitted prompts, manifest, output hash, backend, and generation
time. Bind it to the gate with:

```bash
scripts/run-python scripts/visual_ab_eval.py --record \
  --run-dir <run-directory> --variant <baseline-or-candidate> \
  --case-id <case-id> --task-dir <dedicated-task-directory> \
  --attempt-dir <dedicated-task-directory>/attempts/001
```

After all six slots are locked, use `--blind`, one immutable `--judge` call per
case, and `--results --json`. Run, slot, prompt, input, output, blind image,
mapping, and judgment hashes are rechecked before a verdict is written. Do not
treat unit tests, retrieval metrics, prompt inspection, or an unscored generation
as proof that the candidate improved visual quality.

If later explicit user feedback identifies a critical defect that the blind
review missed, preserve the original result and append the correction with
`visual_ab_eval.py --record-human-feedback --feedback-failure
CASE_ID=VARIANT:CATEGORY --note ...`. Read the current decision with
`--effective-results`; never rewrite the original judgment or `results/result.json`.

## Route by intent

- `new`: create a new composition. Start with one inspected, shot-matched official
  setting sheet or focused official crop per focal character, plus one
  selected-medium style image.
- `edit`: preserve a supplied target. Start target-only when it already provides
  the unchanged identity and medium; otherwise add only the single authority role
  required by the named change.
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

For a manga `wide-shot`, rely on the dedicated scene-economy branch compiled
from the persisted shot. Preserve spatial structure through silhouette, major
axes, overlap, scale, route, and ground contact while deliberately omitting
repeated surface detail. Large white paper, flat black masses, clustered
forms, and distance-based detail falloff are required authoring decisions.
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

Initialize the task and retrieve at most three exact candidates per layer:

```bash
scripts/run-python scripts/plan_art_task.py \
  --slug inuyasha-forest-strike \
  --request "犬夜叉在森林中挥出铁碎牙" \
  --identity-form 犬夜叉=half-demon-form \
  --prop-form 铁碎牙=transformed-form \
  --shot action
```

Inspect the planner's official identity candidates for every focal character.
Choose the single source whose view and visible construction best match the shot;
when the needed face, garment overlap, weapon mount, hand, or footwear occupies
only a small part of a sheet, prepare the smallest focused task-local crop and
record its source hash, crop box, rendered hash, and focus. Then inspect
dynamically ranked selected-medium style candidates. Never filter them to a
predetermined volume or page, character, or character form; rendering retrieval
is driven primarily by the current scene, shot, interaction, and energy. A small
explainable subject-form preference may break a close ranking when the original
also demonstrates the focal character's mark-making or garment value hierarchy;
it never hard-filters the catalog or grants identity authority. A known
high-confusion subject visible in a style candidate but absent from the request
may receive a small explainable ranking penalty; this is never a hard character
filter or identity authority.
Every named canonical weapon or prop must declare its exact form. The official
layer issues a separate exact-form prop search; attach a focused official prop
sheet when needed. A manga action/style image may control foreshortening and
mark-making but never the prop silhouette or construction.
When the identity ledger supplies a topology contract, preserve its counted
features and connected part sequence. Form aliases and topology remain ledger
data so planner, prompt, and QA share one mechanism without prop-specific code.
Do not search `selected-output` unless continuity was requested. Add a
content layer only when identity and style evidence cannot resolve an exact named
fact. Expand beyond three candidates only after recording `MISS` or
`INSUFFICIENT`; never broaden across character form.

After choosing references, fill `brief.scene`, `brief.invariants`, and the
serial evidence results. Layer 2 must explicitly record `HIT` coverage for
character mark-making, hair and face linework, fabric and fold treatment,
garment value hierarchy, and scene rendering. Select one primary style anchor;
use a second only when a core rendering dimension remains visibly unresolved.
Optional scene-material labels describe where the anchor's information budget
must transfer, not additional evidence requirements. Pass a non-empty `--focus` for
each style image that states exactly which of those visible relationships it
controls. Prepare references, compile, and validate in one local
execution. A normal single-character input is one style image plus one
shot-matched official identity image or focused official crop. Hard maximum is
six. Never add a retired identity-card collage.
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
- for a general manga-medium correction, target plus one dynamically selected
  scene-matched manga style image; the bundled guide defines the allowed band but
  does not replace visual evidence;
- target plus at most one dynamically selected style image for any named medium,
  ink, tone, effect, or period treatment.

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
that the user asked to replace. For a manga-medium correction, explicitly allow
removing secondary strands, folds, patterns, texture, shading, and background
information only where it exceeds the selected scene-matched density band while
preserving identity anchors and those structural invariants. Create or update the
durable task record only after a usable preview exists or when user feedback
makes continuity necessary. Technical failures without an output do not require
an empty replacement task.

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

```bash
scripts/run-python scripts/record_attempt.py \
  --task-dir <task-directory> \
  --status candidate \
  --output <candidate.png> \
  --duration-seconds 75 \
  --persist-output \
  --preview-check identity="pass" \
  --preview-check request="pass" \
  --preview-check technical="pass" \
  --json
```

This single post-generation command persists the image, snapshots the exact
submission, records the blocking preview checks, and returns a handoff-ready
output path. Do not run full QA or final validation before showing that preview.

For a modified submission add
`--submitted-prompt <exact-submitted-prompt.md>`. Each immutable attempt stores
brief and manifest snapshots, both compiled and submitted prompt hashes, plus
`submitted-prompt.md`.

After explicit acceptance, record the accepted attempt, complete applicable QA,
read the full workflow contract and quality gate, then run final validation:

```bash
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage final
```

Keep attempts append-only. Only repeated explicit feedback may update the stable
preference profile.

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
