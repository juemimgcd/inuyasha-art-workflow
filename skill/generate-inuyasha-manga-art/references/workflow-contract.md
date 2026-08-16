# Local reference workflow contract

Store generated catalogs, task records, attempts, prompts, and outputs under
`${INUYASHA_WORKFLOW_HOME}/workflow/reference-workflow` by default. The source
configuration uses `${REPO_ROOT}` tokens and resolves them at runtime. A caller
may set `INUYASHA_WORKFLOW_ROOT` or pass `--workflow-root` to relocate generated
workflow data. Keep the original image libraries read-only.

Historical JSON may retain absolute paths from the machine that created it.
Preserve those records verbatim. Resolve configured legacy prefixes only while
reading, using `source-library.json.path_aliases`; never rewrite accepted task or
attempt provenance merely to move between macOS, Windows, or Linux.

## Catalog contract

Run `build_reference_index.py --check` before retrieval. Exit `0` means fresh; exit `3` means missing or stale. Rebuilds reuse unchanged hashes and dimensions. Content-derived image IDs survive renames and moves; legacy path IDs remain aliases.

The catalog indexes images only. Folder names provide inherited metadata, the leaf folder provides a content label, and structured filenames provide exact subject, form, and shot facets. Store `subject_forms` as a character-to-compatible-forms mapping; retain the flat `forms` list only as a compatibility union. A subject and form query must match the same mapping entry. Structured multi-character filenames may use `character-character__form-form__...`. Use annotations only for visual distinctions absent from paths and filenames.

Source configuration may declare `exclude_globs` for derived outputs or work files
that live below a source root but must never gain that source's authority. Each
catalog item stores `eligible_roles`. An explicit annotation such as
`reference-role:content-only` can only narrow the source roles; it can never add
authority that the source itself does not possess. Retrieval and preparation
must enforce item eligibility, not only the source ID.

Historical identity-card collages live under
`workflow/reference-workflow/identity-cards`. They are retired transport bundles,
not catalog sources and not valid inputs for a new generation. Preserve their
recipes, manifests, hashes, images, task manifests, attempts, and completed
benchmark runs so historical provenance remains readable; never copy them into
an official source directory or present them as publisher originals.

`plan_art_task.py` must always issue an official identity search for every focal
character-form. Select one shot-matched official setting sheet, or prepare the
smallest focused official crop when only one face view, garment overlap, weapon
mount, hand, or footwear detail is needed. `prepare_reference_set.py
--identity-card` is a retired compatibility option and must reject new use.
Pre-generation validation rejects any identity-card entry while final validation
continues to understand historical manifests without rewriting them.

Free-text retrieval remains a fallback filter. Rank candidates by explainable
field matches: exact content/action/object first, then interaction/contact,
subject-form and shot/view compatibility, then conservative accepted-attempt
feedback as a tie-breaker. Return `match_reasons` so the inspected candidate set
shows why each item ranked. Do not let a loose path or note substring outrank an
exact controlled tag.

Rendering retrieval remains identity-independent: never add a subject or form
SQL filter merely because a focal character is known. It may apply one capped,
explainable preferred subject-form boost below an exact shot match, so a closely
matched original that also demonstrates the focal character's contour, face,
hair, fabric, or garment values can rank slightly higher. This preference never
creates identity authority and never outranks stronger action, interaction,
contact, object, or shot evidence.

`--intent-text` may translate explicit natural-language phrases into controlled
traits for ranking. Inferred traits are boost-only: they do not hard-filter the
catalog, add evidence authority, create a content layer, or override serial
retrieval. Avoid ambiguous one-character aliases such as `夜` or `风` that also
occur in character names or `画风`; prefer concrete phrases such as `深夜`,
`微风`, `背后拥抱`, `袖中藏手`, and `挥动铁碎牙`. Record the inferred traits in
new retrieval plans so the ranking decision can be reproduced.
Scene-economy and detail-falloff traits are weak rendering tie-breakers; their
combined boost must remain below an exact action or content-object match.

Maintain `references/retrieval-benchmark.json` as a small inspected truth set of
high-frequency intents. Run `benchmark_reference_retrieval.py --check` after
changing trait aliases, annotations, ranking weights, or catalog metadata. The
benchmark must exercise the real search CLI and report Recall@1, Recall@3, MRR,
per-case ranks, and latency. Relevant item IDs must resolve in the current
catalog; do not lower thresholds merely to hide a regression.

Maintain `references/generation-benchmark.json` separately as a fixed-input,
single-generation first-preview benchmark. It measures transport success,
generation duration, form and identity features, costume, anatomy/contact,
composition, and selected-medium rendering. Preparing a run writes prompts,
ordered inputs, and pending score sheets; it does not call a generator. Every
prompt and reference image is snapshotted inside the run with a SHA-256 lock, and
completed visual scores must record a decodable output plus its SHA-256. Scoring
must reject a changed dataset, prompt, input, output, backend, or case list. Never
auto-retry a benchmark case or replace a failed output, because that would hide
first-pass yield and latency.

The active workflow-quality gate is the smaller immutable dataset at
`references/visual-eval-v2.json`. It has exactly three representative `new`
manga cases and two variants, producing exactly six outputs: one baseline and one
candidate output per case. `visual_ab_eval.py --prepare` snapshots the dataset,
revision labels, and one backend under an immutable run lock. Each variant/case
uses a dedicated task with exactly one visual attempt, `attempts/001`, recorded by
the current `record_attempt.py`. That attempt must snapshot the brief, manifest,
compiled prompt, exact submitted prompt, output hash, generator, and generation
time. `--record` rejects a second attempt or a generator that differs from the
run backend, verifies the fixed request, form, shot, medium, intent, and aspect
ratio, and snapshots the attempt plus ordered rendered inputs. It must not
generate, retry, replace, or overwrite an output.

After all six slots pass their complete hash checks, `--blind` builds the visible
A/B directory transactionally: a failure leaves no partial `blind/` state. The
review manifest, visible images, mapping, slot locks, and run lock are hashed.
The reviewer scores the fixed criteria without reading `blind/blind-key.json`,
then records one append-once, hash-locked judgment per case. `--results` rechecks
the run, every slot artifact, all six visible images, the mapping, and all three
judgments before atomically writing the immutable result directory. A candidate
is promotable only with at least two of three wins and zero candidate critical
failures. Ties preserve the baseline. Unit tests, valid schemas, retrieval scores,
or prompt improvements are necessary diagnostics but never substitute for this
visual gate when claiming an image-quality improvement.

An explicit later user rejection may supersede the effective promotion without
changing the immutable blind artifacts. Append a result-hash-bound event to
`human-feedback.jsonl`, name the affected case, variant, and critical category,
and compute the effective verdict from the original result plus all such events.
A critical side is ineligible to win a judgment; if both A and B have critical
failures, the only valid choice is tie/both-fail.

Promote controlled `view-angle:back` and `suitable-for:back-view` annotations to
the structured `back-view` shot facet during rebuild. Keep other visual traits
as search tags unless an explicit promotion rule is documented.

For a multi-view official sheet, keep the source image read-only and prepare a
task-local crop when the requested back view, weapon mount, footwear, hand, or
garment overlap occupies only a small part of the page. Record `crop_box`,
`rendered_content_hash`, `crop_source_hash`, and a non-empty `focus` in the
manifest. Always regenerate the crop from the catalog source. Validation must
recompute the expected pixels from the source and coordinates instead of trusting
manifest hashes alone. The crop keeps the source sheet's authority and may
control only construction visible inside it.

For a strictly local microfix, the prepared target may be a task-local context
crop of the accepted source target. Record the original target path and hash,
`crop_box`, `crop_source_hash`, `rendered_content_hash`, and the exact `focus`.
After generation, composite only the declared `edit_box` back into the original
canvas. Final validation must prove that the output dimensions are unchanged and
all pixels outside `edit_box` still equal the source target. Do not use this mode
for composition changes or edits that cross the crop boundary.

The same crop-and-composite preservation mechanism may be used by an `edit`
task whose target is a recorded but not-yet-accepted candidate. Record the
source task ID, attempt number, attempt status, output path, and immutable output
hash in `brief.candidate_source` and in the target manifest entry's
`source_attempt`. The source attempt remains rejected or otherwise unaccepted;
creating the edit does not create or imply an accepted result. Candidate-local
edits require a declared `edit_box` and exact pixel preservation outside it.

## Task schemas

New tasks use:

- `brief.json` schema 5 with `intent`, `parent_task_id`, `change_category`,
  `change_request`, optional `shot`, optional `content_need`, and
  `content_references`. It may also declare `props`, exact `prop_forms`, and
  `dominant_scene_materials`. New tasks persist the planner's explicit `--shot`;
  legacy briefs without it remain valid.
- `reference-manifest.json` schema 1.
- `qa.json` schema 1.
- `attempts/<NNN>/attempt.json` schema 1 as append-only generation history.
- `result.json` schema 3, written only by accepting a recorded attempt.
- `response-window.json` schema 2 with pre-generation start, optional generation
  start, soft pre/post targets, and an observe-only generation-latency policy.
  Starting a new user request may replace this current-window marker; every
  recorded attempt preserves the phase timing it used. Schema-1 windows remain
  readable as historical data but their total-response SLO is not a current gate.
- `generation-submission.json` schema 1 as the mutable current-call marker. Before
  every image call it locks the response window, exact submitted prompt, endpoint,
  transport, ordered image paths, roles, hashes, dimensions, and byte counts.
  Every recorded attempt snapshots the submitted version immutably.

Do not overwrite rejected attempts. Snapshot the brief, prompt, manifest, and QA
with every attempt. Store explicit user preference feedback in
`preference-events.jsonl`; never infer approval merely because a file exists.

Legacy tasks may remain readable. Audit them with `validate_all_tasks.py`; plan schema normalization with `migrate_art_tasks.py`. Migration is dry-run unless `--apply` is explicitly passed.

If historical evidence cannot be repaired without rewriting what an accepted
generation actually used, create `archived.json` with `archive_art_task.py`.
Normal task validation, reference outcome ranking, and preference learning must
exclude archived tasks while preserving every original file and result.

## Intent contract

### New

- Require one or two selected-medium style screenshots.
- Require official identity coverage for every focal character and exact form.
- Permit at most one exact-focus `content` reference when the requested action,
  object, creature, effect phase, or spatial fact needs separate visual evidence.
- Permit at most one selected-output continuity reference.
- Keep the normal total at two to five images and hard maximum at six.
- Design a new composition unless the user supplied a distinct composition reference.
- Fast default: one style screenshot plus one official identity image per focal character. Add a second style screenshot only when the first is visibly insufficient.
- First-preview rule: after the bounded evidence set passes pre-generation
  validation, make one generation call and hand off the first usable preview.
  Do not generate aesthetic alternatives before user feedback.

### Edit

- Require exactly one target and place it first.
- Permit at most one style screenshot.
- Require official coverage when identity, form, costume, or anatomy is being changed or repaired.
- Use no more references than the named change needs.
- Permit one separately planned exact-focus content reference only when the target
  cannot supply the changed content.
- Fast default: target only when it already supplies the unchanged identity and
  medium; otherwise add only the single authority role required by the named
  change. A target plus unrelated style or continuity evidence is not a default.
- For a general manga-medium correction, use the target plus one dynamically
  selected, scene-matched manga style screenshot. The bundled corpus-derived
  guide defines the QA band but does not replace visual evidence. Do not attach
  a fixed volume or page.
- For a target-only first preview, inspect the supplied target and generate before
  locating a historical task or completing durable task bookkeeping. Create or
  update the task record after a usable preview exists. Require pre-generation
  task preparation only when a proxy, crop, continuity inheritance, or additional
  authority reference is actually needed.
- For bounded follow-up feedback on a recorded candidate, create a child `edit`
  with that attempt output as the first target and use crop-and-composite. Verify
  the recorded output hash before preparation. Do not require or fabricate an
  accepted parent result, and do not continue under the original `new` manifest.
- When a candidate follow-up crosses a safe crop boundary, create the child with
  `continue_art_task.py --from-attempt ... --full-canvas`. It must still record
  that candidate as the first target; never attach it invisibly to the original
  `new` task.

### Microfix

- Require a validated parent task and exactly one target.
- Inherit the parent's medium, forms, scene, aspect ratio, invariants, and evidence.
- Re-open only the changed category.
- Permit at most one style screenshot and prohibit a redundant continuity image.
- Use target-only for composition, background, and polish unless new evidence is explicitly needed.
- Use target plus official identity for identity, form, costume, or anatomy.
- Use target plus the smallest focused official crop for construction changes involving attachment, overlap, perspective, or contact.
- Use target plus one style screenshot for medium or tone.
- Hard-limit the prompt to 1,800 characters and the reference set to five images.

## Serial retrieval contract

For a new task, run the layers in this order and record `HIT`, `MISS`,
`INSUFFICIENT`, or an allowed `SKIP` before advancing:

1. `official` for canonical identity and exact form.
2. `manga-curated` or explicit `tv-curated` for rendering only.
3. Optional exact content evidence. Search the selected-medium curated source first.
   Open the other curated medium only after the selected-medium content search is
   recorded as `MISS` or `INSUFFICIENT`. Record `SKIP` when no separate content
   evidence is needed.
4. `selected-output` for explicitly requested accepted continuity only; otherwise
   record `SKIP` and do not search it.

Layer 1 includes a separate exact-form search for every declared canonical
weapon or prop. A prop-only official sheet is valid identity/construction
authority for that named prop and does not have to depict a focal character.
Style and content images may not substitute for canonical prop construction.

A content query is one exact structured filename term, tag, or content label;
use inspection to choose the catalog's term rather than a loose substring. A
style-layer `HIT` resolves rendering only and never counts as a content-layer
`HIT`. Conversely, a cross-medium content hit never weakens the requirement for
selected-medium style evidence. The selected content reference must have one
non-empty exact `focus`, and the normal budget is one image.

Start identity and content layers with exact subject + form + shot. If the shot
is empty or insufficient, remove only the shot. Never broaden identity or content
across form. Rendering/style retrieval is identity-independent: search by current
scene, shot, interaction, atmosphere, and action energy without subject or form
filters. A known high-confusion subject visible in a style candidate but absent
from the request may receive a small, explainable ranking penalty; this is never
a hard filter, an identity match boost, or a grant of identity authority. Then
remove shot before declaring `MISS` or `INSUFFICIENT`. 犬夜叉
`default-form` may alias `half-demon-form` only in configured screenshot sources;
it never aliases human or full-demon form.

The complete local manga PDFs are offline calibration/evaluation material and a
cold fallback for curating a focused screenshot only after the indexed curated
layer is recorded insufficient. Never attach a whole volume to a generation
call, present the corpus as newly created official material, upload it as
"training data", or claim that this workflow fine-tunes the image model.

For multi-character evidence, bind every requested form to its named character.
Never satisfy `戈薇=default-form` merely because another character in the same
image is indexed with `default-form`, and never leak 犬夜叉 form aliases to 戈薇.

Do not rerun unchanged parent evidence for a microfix. Reuse it only when the parent task, catalog item IDs, medium, and identity forms remain valid.

Show at most three exact candidates per layer by default. Expanding first to four
and then to six
requires a recorded `MISS` or `INSUFFICIENT`; large speculative contact sheets
are not part of the normal path.

## Reference authority and order

Manifest order is:

1. `target`
2. `style`
3. `identity`
4. `form`
5. `continuity`
6. `composition`
7. `content`

Official sheets control canonical identity and construction only. Manga
screenshots from `origin-photos` control selected-medium character contour,
face/hair/fabric/fold mark-making, garment value hierarchy, and scene rendering
only. TV screenshots control the corresponding TV palette, contour, fabric,
cel-shadow, and value relationships only. Selected outputs control approved
continuity only. A target controls every unchanged pixel relationship and
composition choice in an edit.

When the official layer records `MISS` or `INSUFFICIENT` for one exact requested
form, one selected-medium original may be assigned the `form` role. It controls
only the visible age/form state (proportions, silhouette, face construction,
hair-to-ear relationship, and form-specific garment scale). It does not become
general identity or style authority, and it cannot come from the other medium.

A `content` reference controls only the exact visible action state, object or
creature configuration, effect phase, or spatial relationship named by `focus`.
It cannot control identity, form, costume, palette, rendering style, framing,
background treatment, or story staging. When its source medium differs from the
task medium, record `evidence_medium`, `cross_medium: true`, and a conversion such
as `tv-to-manga-content`; translate the named content into the selected-medium
style instead of averaging the two media.

Use `content_need.provenance: fallback-medium-original` only when inspection
establishes that the design is genuinely original to the fallback medium. The
manifest must repeat that provenance, the reference must actually be
cross-medium, and the prompt must label the result as a source-medium-derived
adaptation rather than selected-medium canonical evidence. Otherwise use
`observed-content`.

Official identity authority includes observable anatomy, costume layering,
weapon or prop construction, attachment, and relative scale. A focused official
crop does not gain scene-composition or rendering-style authority.

Official identity evidence owns which garment components, overlaps, patterns,
and accessories exist. Selected-medium rendering evidence owns how those same
parts are drawn and separated by relative paper-white, flat-black, halftone, or
TV cel/value relationships. Never copy a style source's costume design or let
its tone assignment redefine official garment construction. Before generation,
Layer 2 must record `HIT` coverage for character mark-making, hair and face
linework, fabric and fold treatment, garment value hierarchy, and scene
rendering. Choose one primary style anchor. A second is permitted only when a
core rendering dimension remains visibly unresolved. Optional scene-material
labels are transfer scope for the primary anchor's information budget; they do
not require material-by-material references. Every style manifest entry must
carry a non-empty exact focus.

Every form-sensitive task must declare an identity form. Reject a reference depicting a requested character in another or unclassified form, even when the sheet was selected for a weapon or costume detail. The only exception is a selected-medium `content` crop with a non-empty exact focus when human inspection confirms that the prepared crop excludes the form-conflicting character and shows only the requested object or spatial fact. Preserve the source item, crop coordinates, source-pixel hash, rendered hash, and focus. This exception never applies to full images or to `identity`/`form` roles.

## Prompt contract

Generate prompts from the current brief and manifest with `compile_prompt.py`.

- New prompts may describe the complete new scene but must remain under 7,000 characters.
- Edit prompts must remain under 3,500 characters.
- Microfix prompts must remain under 1,800 characters and state one change category.
- Always state each input's limited authority.
- For cross-medium content, repeat the exact focus and explicitly discard the
  source medium's palette, contours, shading, textures, background grammar,
  framing, and character rendering.
- For manga, forbid copying style-reference characters, dialogue, panels, layout, pose, and story.
- For manga, bridge the authorities explicitly: preserve every official garment
  component, overlap, pattern, and accessory while applying the style reference's
  character contour, face/hair/fabric/fold treatment, and relative paper-white,
  flat-black, and restrained middle-tone hierarchy to those same parts.
- For manga, compile the corpus-derived scene-conditioned density band: the
  output must read as direct, page-ready late-1990s serialized manga rather than
  either a polished monochrome illustration or generic under-rendered line art.
  Preserve identity-bearing eyes, bangs, jaw, hair silhouette, costume layers,
  contact, and required setting cues. Never translate offline provenance into a
  fixed volume/page query or input; select style evidence dynamically.
- For a manga `wide-shot`, compile a dedicated scene-economy clause. Treat
  coherent axes, scale, depth, overlap, and ground contact as structural
  completeness. Treat information as a finite narrative budget: require authored
  paper-white intervals, grouped shapes, selective contours, restrained tones,
  and strong detail falloff. Retrieve these as positive observable traits rather
  than enumerating unwanted finishes or individual surfaces. When the stored
  deliverable is `illustration`, the
  generator-facing format must call it a single borderless serialized-manga
  panel. Legacy briefs with no shot use the general clause.
- For a manga `wide-shot` edit, compile an additional preservation lock. Unless
  the named request explicitly changes one, preserve the target's framing, crop,
  camera distance, character scale and placement, major object positions,
  perspective axes, and overall black-white distribution. Reject both uniform
  whole-canvas simplification and unauthorized dramatic re-authoring: do not
  enlarge the character, recrop or recompose, add large new black areas, or
  intensify the staging merely to advertise manga emphasis. Correct mark-making
  locally through contour taper and breaks, clustered marks, selective density,
  and distance falloff inside the approved composition.
- For a manga `medium` edit, preserve identity, pose, expression, composition,
  spatial relationships, and named content, but move finish into the selected
  style reference's density band. Remove only redundant secondary strands,
  folds, patterns, material texture, smooth shading, and background detail.
  A grayscale/tone substitution alone fails, and so does stripping identity or
  scene construction into a sparse generic outline.
- Do not add numeric or percentage caps for strands, folds, tones, rain lines,
  textures, or background marks unless that exact relationship is observable in
  the selected style evidence.
- Default to no lettering, balloons, borders, logo, signature, or watermark.
- Refer to attached images by manifest input order and role. Do not put opaque catalog hashes into the generator-facing prompt.

Machine-readable identity ledgers may expand canonical observable details and
positive prop topology (`connected_sequence` plus counted features). Planner,
prompt, and QA consume the same ledger; production code must not branch on a
past failed image. Prop form inference may separate `explicit` form phrases from
weaker `context` actions; an explicit match always wins. A learned preference
profile may contribute only traits
supported by repeated explicit accepted feedback. Refresh it after an accepted
attempt as a derived-cache side effect; a refresh error must be reported without
rolling back, duplicating, or misreporting the accepted attempt. Neither may
override the current request or source authority.

## Attempt and feedback contract

Submit compiled `prompt.md` verbatim by default and do not append unrecorded
generator-only instructions. If transport wrapping or an intentional change is
unavoidable, save the exact text and pass it to `record_attempt.py
--submitted-prompt`; every attempt snapshots compiled and submitted prompt hashes
plus `submitted-prompt.md`. Record every generated result before the next
generation. Use `candidate` for a usable preview pending user confirmation,
`rejected` only for a failed visual result, and `accepted` only after explicit
approval. Rejected attempts require at least one structured failure category.
Accepted attempts may include explicit feedback and preference tags. A rejected
candidate does not automatically discredit every reference used to make it: pass
`--reference-blame <item-id>` only when the failure is directly attributable to
that manifest item. Generator drift, preservation failure, and prompt failure
remain recorded without lowering reference ranking.

Reference outcome ranking is a conservative tie-breaker after exact source, subject, form, shot, and query relevance. Accepted attempts support every reference in the accepted set; rejected attempts count only against explicitly blamed items. New or sparsely observed references stay near a neutral prior so one success or failure cannot dominate retrieval.

Record available generation timing with `duration_seconds`. A technical failure
may receive one retry only after a meaningful input, wording, or transport change.
Record an `error` attempt with a `technical` failure immediately after the image
call returns an error, before commentary or retry. Recording any attempt closes
the current response window to `recorded` and stores its attempt number and
status, so an interrupted turn cannot leave generation telemetry suspended.
After two consecutive technical failures in the same task, stop generation and
surface the blocker. Re-run pre-generation validation before every retry; it
must reject a third generation in the same uninterrupted technical-error streak,
even when the prompt or manifest changed. A visual rejection should reopen only
its highest-priority failure category; make at most one scoped follow-up call,
then wait for user feedback instead of restarting all retrieval layers or
running a third automatic full-canvas revision.

A network failure whose generation call lasted at least 180 seconds is treated as
having exhausted the image client's internal transport retries. Recording it sets
`transport_retry_exhausted: true` and blocks an outer retry across response-window
resets. A later explicit user request may authorize exactly one new call through
`start_response_window.py --authorize-network-retry --authorization-note ...`;
the authorization is bound to the blocking attempt number. Prompt shortening or
changing image transport without explicit user authorization does not bypass this
stop.

Do not impose a fixed total-response SLO on model generation. Measure three phases
separately: controllable pre-generation overhead, external generation latency,
and controllable post-generation overhead. Default soft targets are 30 seconds
before generation for `edit` and `microfix`, 90 seconds for `new`, and 30 seconds
after generation; tasks may override them. Exceeding a soft target is a warning,
never a generation or retry blocker. New tasks create `response-window.json`; a
new request on an existing task resets phase timing without erasing attempts.
Call `start_response_window.py --mark-generation-started` immediately before the
image call, after `prepare_generation_submission.py` snapshots the exact call and
pre-generation validation passes. `record_attempt.py` stores `generation_seconds`,
`pre_generation_seconds`, `post_generation_seconds`, target results, and combined
controllable overhead. `reference_feedback_report.py` reports these distributions
separately; legacy total-response SLO fields remain historical only.

For follow-up edits, batch all sub-second local preparation into one execution
boundary; then make one generation call and one blocking visual check before
handing off the preview. A standard new image adds only one serial candidate
inspection before the same prepare/generate/handoff sequence. Candidate previews
do not require completed `qa.json` or final validation. Those are acceptance
gates, not preview gates. Do not re-read the quality gate or perform a second
full-size inspection in the same turn unless the first inspection found an
actionable risk.

Pre-generation validation reports elapsed controllable preparation and whether
its soft target was met. It does not estimate remaining model time or block a
retry based on elapsed seconds. Two technical failures in the same response
window still block a third call by default. A later explicit user request may
open a new window in the same task; creating a replacement task solely to reset
errors is a process violation.

A full-canvas external target may use a manifest-tracked downscaled JPEG transport
proxy when upload size is a likely failure condition. The manifest must preserve
the original path, original content hash, source and rendered dimensions, proxy
hash, maximum edge, and JPEG quality. The proxy is transport-only and does not
replace the original target's authority. Validation must reject changed source or
proxy bytes and inconsistent dimensions. A crop-and-composite target may not also
use a full-canvas transport proxy.

## Validation contract

Before generation:

```bash
scripts/run-python scripts/validate_art_task.py \
  --task-dir <task-directory> --stage pre-generation
```

Validation must reject a content reference with no planned focus, more than one
content image, a non-curated content source, a wrong conversion marker, or a
cross-medium selection whose evidence log lacks selected-medium `MISS` or
`INSUFFICIENT` followed by a fallback `HIT`. It must also reject using a
non-selected medium as `style`.

For a manga `wide-shot`, generated QA must separately test scene economy and
spatial construction: correct perspective or abundant construction marks do not
pass when foreground and distance share uniformly fine surface detail.
For every declared canonical prop, generated QA must test the exact official
form. A sword must preserve one continuous grip-to-guard-to-blade force axis and
its canonical connected silhouette; duplication, bifurcation, or disconnected
parallel blades are blocking construction failures.
For a manga `wide-shot` edit, generated QA must also test preservation of target
framing, camera distance, character scale and placement, major objects,
perspective axes, and overall black-white distribution. Fail an edit that
substitutes a more dramatic composition or globally emptier finish for the named
mark-making correction.

After acceptance, require all applicable QA checks to be `pass` or `n/a`, require
a recorded accepted attempt and existing output, and run final validation. Before
acceptance, a usable preview needs a direct blocking check for identity/form,
requested edit scope, applicable medium density band, and technical integrity.
Fix failures in this order: identity/form, medium leakage or under-rendering,
anatomy/costume, composition, background/tone, polish.

For every full-body, multi-character, foreshortened, or prop-bearing image, also
verify one coherent depth system, continuous support/contact chains, explicit
occlusion order, ground contact, and the absence of floating or interpenetrating
parts.
