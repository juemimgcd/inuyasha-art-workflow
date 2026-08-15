---
name: generate-inuyasha-manga-art
description: "Generate, edit, microfix, or art-direct character-accurate Inuyasha manga or TV images with official identity sheets, selected-medium originals, accepted-output continuity, intent-aware prompts, append-only attempt feedback, and validated reference manifests. Use for 犬夜叉角色、漫画版、原著漫画风格、TV版、动画版画风、设定集、角色立绘、漫画插图、漫画分镜、动画场景、战斗、妖怪、连续性修图、局部修图、reference manifests, prompt refinement, or image-workflow maintenance."
---

# Generate Inuyasha art

## Keep authority separate

- Official setting sheets control identity, form, anatomy, costume, weapon,
  prop, attachment, and scale.
- One inspected selected-medium original normally controls rendering grammar.
- A separately planned curated `content` image may control only one exact visible
  action, object, creature, effect phase, or spatial fact.
- A `selected-output` controls accepted continuity only when continuity is asked for.
- The user target controls the exact instance and every unchanged region of an edit.
- The request controls the new scene or named change.

Never let a style image control identity or copy its characters, dialogue,
layout, pose, or story. Never let cross-medium content control style or identity.

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

Immediately before the image call, mark the phase transition in the same
execution boundary that launches generation:

```bash
scripts/run-python scripts/prepare_generation_submission.py \
  --task-dir <task-directory>
scripts/run-python scripts/start_response_window.py \
  --task-dir <task-directory> --mark-generation-started
```

The submission snapshot binds the exact compiled prompt and ordered input image
bytes to the call. For tracked target-only edits, `prepare_quick_edit.py` performs
task initialization, target preparation, prompt compilation, submission
snapshotting, and pre-generation validation in one local command.

Optimize only work the agent controls:

- Target-only first edit preview: inspect the target, make one image call, then
  perform one blocking check and immediate handoff. Do not locate a parent task,
  create a full task workspace, prepare a proxy, or run task validation first
  unless continuity, an additional authority reference, or fragile transport
  actually requires it.
- Tracked edit: at most three execution boundaries — one batched local
  preparation, one image call, one blocking check plus save/record/handoff.
- Standard new image: at most four boundaries — one serial candidate inspection,
  one batched prepare/compile/validate step, one image call, one blocking check.
- Make one generation call and show the first usable preview. Do not silently
  generate alternatives or aesthetic polish.
- Batch task updates, attempt recording, reference preparation, prompt compilation,
  and pre-generation validation when their inputs are already known.
- Candidate previews require one direct check for identity/form, requested edit
  scope, and technical integrity. Inspect the image already returned by the image
  tool; call `view_image` only when that result is not visually available. Do not
  fill all of `qa.json`, re-read the quality gate, or run final validation before
  user acceptance.
- After a usable output, combine copying to the workspace, attempt recording, and
  any required preview metadata in one local execution. Hand off immediately;
  aesthetic alternatives and final QA wait for user feedback.
- A first technical failure may be retried only when the input, wording, or
  transport condition changes. Retry limits depend on consecutive technical
  failures, never on elapsed generation time.
- A network/transfer error after at least 180 seconds is treated as an exhausted
  long-running call. Do not make an outer automatic retry unless the current
  response window was explicitly authorized with
  `--authorize-network-retry` and an `--authorization-note`.
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

## Route by intent

- `new`: create a new composition. Start with one official identity image per
  focal character and one selected-medium style image.
- `edit`: preserve a supplied target. Start target-only when it already provides
  the unchanged identity and medium; otherwise add only the single authority role
  required by the named change.
- `microfix`: continue an accepted parent task, inherit validated evidence, and
  reopen only one change category. Use crop-and-composite for a bounded region.

Default ambiguous medium requests to `manga`. Use `tv` only when explicitly asked.

## Fast new-image path

Initialize the task and retrieve at most three exact candidates per layer:

```bash
scripts/run-python scripts/plan_art_task.py \
  --slug inuyasha-forest-strike \
  --request "犬夜叉在森林中挥出铁碎牙" \
  --identity-form 犬夜叉=half-demon-form \
  --shot action
```

Inspect official identity first, then the selected-medium style candidates. Do
not search `selected-output` unless continuity was requested. Add a content layer
only when identity and style evidence cannot resolve an exact named fact. Expand
beyond three candidates only after recording `MISS` or `INSUFFICIENT`; never
broaden across character form.

After choosing references, fill `brief.scene`, `brief.invariants`, and the
serial evidence results. Prepare references, compile, and validate in one local
execution. Normal single-character input is two images. Hard maximum is six.

## Fast edit path

Place the target first. Use:

- target only for composition, background, polish, or any change already resolved
  by the target;
- target plus one official identity reference for identity, form, costume, or
  anatomy;
- target plus the smallest focused official crop for construction/contact;
- target plus at most one selected-medium style image for medium or tone.

For a first preview that needs only the supplied target, do not create or search
for a historical task before generation. The current target already controls
identity, medium, composition, and unchanged regions. Create or update the durable
task record only after a usable preview exists or when user feedback makes
continuity necessary. Technical failures without an output do not require an
empty replacement task.

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
pass `--full-canvas` to make that choice explicit.

For wide-shot manga edits, the compiled prompt must preserve framing, camera,
character scale, pose, action geometry, background, and every unchanged region.
It must also forbid converting the image into a portrait or character sheet.

## Attempts and acceptance

Record every candidate before another generation. Rejections require a structured
failure; errors require `technical`; blame a reference only when it visibly caused
the defect:

```bash
scripts/run-python scripts/record_attempt.py \
  --task-dir <task-directory> \
  --status candidate \
  --output <candidate.png> \
  --persist-output \
  --preview-check \
  --duration-seconds 75 \
  --json
```

After explicit acceptance, record the accepted attempt, complete applicable QA,
read the full workflow contract and quality gate, then run final validation:

```bash
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage final
```

Keep attempts append-only. Only repeated explicit feedback may update the stable
preference profile.

## Maintenance and deeper resources

- `references/workflow-contract.md`: full schemas, lifecycle, compatibility,
  cross-medium, migration, and final-acceptance rules.
- `references/character-identity.md` and `identity-ledgers.json`: identity routing.
- `references/style-guide.md` and `tv-style-guide.md`: medium construction.
- `references/quality-gate.md`: full-size final QA.
- `references/visual-traits.md`: controlled retrieval annotation.

For maintenance, run `reference_feedback_report.py`, `validate_workflow.py`, and
the relevant task validation. Preserve original libraries and historical attempts.
When syncing the installed skill back into its packaging repository, use the
repository sync tool in check/dry-run mode first; it copies only allowlisted
package files and must not replace catalog, task, library, or generated runtime
data.
