# Inuyasha art workflow improvement plan

Status: Part 1 is complete in the live installed skill and implemented on this
portable-package branch as of 2026-08-30. Parts 2 and 3 remain proposals. The
package branch was updated through the scoped sync tool after staged compile,
unit, and workflow validation; no test files were changed.

Part 1 activation evidence:

- Newly initialized, schema-marked manga tasks compile from authority-scoped
  semantic units; legacy tasks, edit, and microfix remain on the previous path.
- `prompt-compile.json` records included, merged, compacted, omitted, conflict,
  projection, and required-coverage decisions. Validation recompiles it from the
  current brief and manifest before it is hash-bound into submissions and
  immutable attempts.
- `compile_prompt.py --explain --json` is read-only.
- Close-up and upper-body projection records non-visible identity/prop details;
  controlled opposite body or face directions block compilation.
- The corrected six-image, three-case manga visual gate
  `20260830-part1-semantic-compiler-final-gate` used matching ordered reference
  hashes in each pair and passed with three candidate wins, zero baseline wins,
  and zero candidate critical failures.

This plan adapts three useful ideas from
[`awesome-gpt-image-2`](https://github.com/freestylefly/awesome-gpt-image-2)
without importing its community prompt/image library or weakening this
workflow's evidence authority, exact-form retrieval, append-only attempts, and
explicit acceptance rules.

The three changes are:

1. A real prompt compilation stage with semantic units, authority-aware conflict
   handling, visibility projection, budgeting, and an omission report.
2. A local read-only visual browser for indexed reference material.
3. A local casebook derived from immutable generation attempts and later user
   decisions.

The implementation should produce one compiler improvement and one local
workflow browser with separate **References** and **Attempts** views, rather than
three unrelated systems.

## Runtime and package boundary

This repository is a portable package checkout, not the live Codex runtime.

- Live installed skill:
  `/Users/jquery/.codex/skills/generate-inuyasha-manga-art`
- Live workflow data:
  `/Users/jquery/Documents/inuYasha-design/reference-workflow`
- Portable package checkout:
  `/Users/jquery/Documents/inuyasha-art-workflow`

Implementation should begin in the live installed skill. Package synchronization
is a separate reviewed step and must use `tools/sync_installed_skill.py` with an
explicit include list. Never bulk-copy the live skill into this repository and
never replace the package-specific `references/source-library.json`.

## Goals

- Make prompt construction inspectable and deterministic.
- Preserve every hard user invariant and evidence-authority boundary.
- Remove semantic repetition without truncating arbitrary strings.
- Explain included, merged, omitted, and conflicting prompt facts.
- Make the indexed reference library visually browsable without creating a
  second catalog.
- Make accepted, candidate, rejected, and error histories searchable without
  rewriting attempts or inflating generation counts.
- Keep the gallery and casebook read-only derived views.

## Non-goals

- Do not import the upstream project's prompts or images into the official,
  manga-curated, TV-curated, or continuity libraries.
- Do not use generic style/category tags as identity, form, construction, or
  scene authority.
- Do not add Supabase, authentication, payments, analytics, React, Vite, or a
  new database.
- Do not let the gallery directly mutate manifests, annotations, attempts,
  results, or the preference profile.
- Do not treat a shorter prompt, a valid schema, or a passing structural check
  as proof of improved generated-image quality.

## Data flow

```text
brief.json + reference-manifest.json + identity ledgers + rendering map
                                |
                                v
                      prompt compilation units
             normalize / merge / conflict / project / budget
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
                prompt.md          prompt-compile.json
                    |                       |
                    +------ submission -----+
                                |
                                v
                       immutable attempt snapshot


catalog.sqlite3 ----------------------> gallery: References
tasks/*/attempts/*/attempt.json ------> gallery: Attempts
reference_feedback_report.py --------> gallery: Summary
```

## Part 1: Prompt compilation stage

### Problem

The current compiler already has the right source material: the task brief,
manifest roles, official identity ledgers, rendering map, topology constraints,
scene-economy rules, and intent-specific prompt limits. The missing layer is
semantic compilation before prose rendering.

Today, helpers produce prose fragments which are assembled into a large string.
The final length check can reject an oversized prompt, but it cannot explain
semantic duplication, resolve contradictions, project only visible constraints,
or safely remove low-value text.

### Compilation unit

Use plain dictionaries rather than a plugin framework or class hierarchy. A
minimal unit is:

```json
{
  "id": "identity.inuyasha.human-form.face",
  "text": "Preserve the official human-form face construction.",
  "authority": "official",
  "scope": "character",
  "priority": "critical",
  "required": true,
  "source": "identity-ledger"
}
```

Required fields:

- `id`: stable semantic identifier used for deterministic merging.
- `text`: final generator-facing wording if the unit is included.
- `authority`: `request`, `target`, `official`, `character-style`,
  `scene-style`, `content`, `workflow`, or `preference`.
- `scope`: `character`, `scene`, `composition`, `prop`, or `global`.
- `priority`: `critical`, `high`, `normal`, or `optional`.
- `required`: whether budget handling may omit the unit.
- `source`: the brief, manifest, identity ledger, rendering map, preference
  profile, or workflow default that produced it.

Do not use fuzzy text similarity or another model to decide whether two units
are the same. Merge only stable semantic IDs or explicitly declared aliases.

### Priority and authority

Authority remains domain-scoped. There is no valid global rule such as
"official always overrides the request" because each source controls a
different relationship.

| Priority | Content | Budget behavior |
| --- | --- | --- |
| Critical | Explicit request, count, direction, negative constraints, identity/form, canonical topology, edit boundary | Never omit |
| High | Applicable evidence authority, character/scene rendering scope, focal hierarchy, contact chain | Preserve; merge only equivalent units |
| Normal | Scene materials, era cues, depth treatment, general medium calibration | Merge or compact at unit boundaries |
| Optional | Repeated disclaimers, generic reminders, learned preference wording | May omit with a recorded reason |

Conflicts are evaluated only within the same semantic concept and scope.
Examples that must block compilation include:

- `human-form` combined with half-demon ears.
- A one-person invariant combined with a default crowd.
- `no-weapon` combined with a Tessaiga construction unit.
- `change_scope=scene` combined with permission to redraw character folds.
- Opposite body or face directions for the same requested moment.

### Compilation stages

#### 1. Normalize

Convert the brief, manifest, identity ledger, rendering map, target locks, and
workflow defaults into compilation units. Keep source provenance on every unit.

#### 2. Merge

Merge exact semantic duplicates. For example, several helpers may require that
a style reference not control identity; the final prompt needs one clear
authority statement, not several paraphrases.

#### 3. Resolve conflicts

Within one concept and scope, apply explicit rules:

1. Current user request and hard invariants.
2. The valid authority for that domain: target for unchanged edit content,
   official evidence for identity/construction, scoped style evidence for
   rendering, and exact-focus content evidence for its one named fact.
3. Structured ledger and rendering-map derivations.
4. Workflow defaults.
5. Learned preferences.

An unresolved critical conflict fails before `prompt.md` is written.

#### 4. Project visible constraints

Project only requirements applicable to the requested shot and intent:

- `face` or `close-up`: retain face, hair, expression, visible costume overlap,
  and applicable prop contact; omit feet and ground-contact prose unless the
  request makes them visible or consequential.
- `upper-body`: retain face, hair, collar, sleeve, hands, and visible prop
  connections; compact distant-scene construction.
- `wide-shot`: retain exact identity/form silhouettes and hard construction,
  but move the information budget toward scale, axes, overlap, paper white,
  grouped values, and distance falloff.
- `edit`: emit only the named change plus explicit target preservation and any
  new authority needed for that change.
- `microfix`: reopen one change category and compile all other categories into
  one target-lock statement.

Projection must never remove an explicit user requirement merely because it is
unusual for the selected shot.

#### 5. Allocate the prompt budget

Use the current intent limits as hard guards:

- `new`: 8,000 characters.
- `edit`: 4,000 characters.
- `microfix`: 2,000 characters.

Include all critical and high units first. Compact normal units next, then omit
optional units only at complete unit boundaries. Never truncate the final
string or cut a rule in half.

#### 6. Verify required coverage

Before accepting the compiled prompt, verify that it still contains:

- The exact requested moment and focal hierarchy.
- Every focal character and exact form.
- Every explicit count, direction, presence, and absence requirement.
- Canonical prop forms and topology when applicable.
- Edit or microfix preservation boundaries.
- Correct authority wording for every submitted input.
- Required manga medium and scene-economy relationships.

### Compilation report

Write a companion artifact beside `prompt.md`:

```text
prompt-compile.json
```

Suggested schema:

```json
{
  "schema_version": 1,
  "intent": "new",
  "limit": 8000,
  "rendered_characters": 5260,
  "included": [],
  "merged": [],
  "omitted": [],
  "conflicts": [],
  "required_coverage": {
    "request": true,
    "identity": true,
    "form": true,
    "negative_constraints": true,
    "authority_boundaries": true
  }
}
```

Every omitted unit must record a stable reason such as:

- `not-visible-in-close-up`
- `duplicate-of:<unit-id>`
- `outside-change-scope`
- `optional-budget-prune`

The exact report must be hash-bound in `generation-submission.json` and copied
into the immutable attempt snapshot alongside compiled and submitted prompts.

### CLI behavior

Extend `compile_prompt.py` with an explain mode:

```bash
scripts/run-python scripts/compile_prompt.py \
  --task-dir <task-directory> --explain --json
```

The explain command should show the compilation plan without changing the
submitted prompt. This allows the new model to be audited before activation.

### Activation stages

#### Stage A: Explain only

- Build units and the report.
- Keep `prompt.md` byte-identical to the current compiler output.
- Compare real tasks for missing, duplicated, or conflicting concepts.
- Do not claim a generated-image improvement.

#### Stage B: Activate for `new` manga tasks

- Render `new` manga prompts from units.
- Leave `edit` and `microfix` on their current path.
- Bind `prompt-compile.json` into submission and attempt provenance.
- Run existing structural checks and the relevant three-case visual A/B gate.
- If rendering-map or manga finish wording changes, also run the focused manga
  style gate.

#### Stage C: Consider edit and microfix later

Extend the compiler only after the `new` path demonstrates a real benefit.
Do not rewrite all three paths in one change.

### Expected implementation files

- `skill/generate-inuyasha-manga-art/scripts/task_workflow.py`
- `skill/generate-inuyasha-manga-art/scripts/compile_prompt.py`
- `skill/generate-inuyasha-manga-art/scripts/prepare_generation_submission.py`
- `skill/generate-inuyasha-manga-art/scripts/record_attempt.py`
- `skill/generate-inuyasha-manga-art/scripts/validate_art_task.py`
- `skill/generate-inuyasha-manga-art/references/workflow-contract.md`
- `skill/generate-inuyasha-manga-art/SKILL.md`

## Part 2: Local reference browser

### Purpose

The current workflow already has strict catalog domains, exact character/form
eligibility, controlled traits, relevance explanations, reference performance,
and contact-sheet generation. The missing piece is an efficient visual browsing
surface for human inspection.

The browser is a derived view of `catalog.sqlite3`; it is not a retrieval engine
or an evidence authority.

### Data source

Open the current catalog read-only and expose existing fields:

- `item_id`
- `source_id`
- `reference_domain`
- `relative_path` and source path
- `subjects` and `subject_forms`
- `shot_types`
- controlled tags, including view angle and scene traits
- `eligible_roles`
- dimensions and content hash
- certified style-anchor status
- accepted/rejected reference-use counts and smoothed performance
- retrieval match reasons when opened from a query

Do not create a second catalog and do not infer new authority from filenames in
the browser.

### References view

Provide filters for:

- Manga or TV medium.
- `identity`, `character-style`, `scene`, or `continuity` domain.
- Character and exact form.
- Shot and view angle.
- Canonical scene ID.
- Scene economy, authored negative space, black mass, tone, and detail falloff.
- Eligible evidence role.
- Certified style-anchor status.
- Historical accepted/rejected use.

Each reference card should display:

- Thumbnail.
- Item ID and domain.
- Subject/form and shot/view facets.
- Controlled tags and content label.
- Source path and hash.
- Historical reference outcome summary.

The detail view may offer:

- Copy item ID.
- Copy source path.
- Copy an equivalent `browse_curated_styles.py` query.

It must not offer a direct "add to manifest" action. Selection still goes
through existing bounded retrieval, preparation, manifest ordering, and
pre-generation validation.

### Implementation

Add one builder:

```text
skill/generate-inuyasha-manga-art/scripts/build_workflow_gallery.py
```

Generate derived output under the selected workflow root:

```text
workflow/reference-workflow/gallery/
├── index.html
├── references.json
├── attempts.json
└── thumbnails/
```

Implementation constraints:

- Python reads SQLite and task JSON.
- Use native HTML, CSS, and JavaScript.
- Add no frontend or server dependency.
- Cache thumbnails by source content hash.
- Never modify or relocate original images.
- Never write generated gallery files into a configured source library.
- Serve locally with a small standard-library HTTP server when browser security
  prevents `file://` from loading JSON or images.

### UI requirements

- Clear primary action: filter/search the collection.
- Loading state while JSON is read.
- Empty state when no rows match.
- Error state for missing JSON, missing images, or invalid rows.
- Hover, focus-visible, and disabled states.
- Intentional mobile, tablet, and desktop layouts.
- Keyboard-accessible filters and detail dialog.
- Verification in Safari and the primary Chromium-based browser.

### Safety boundary

The gallery may display catalog fields and generated thumbnails only. It must
not modify:

- `catalog.sqlite3`
- `annotations.jsonl`
- `reference-manifest.json`
- `brief.json`
- attempt or result files
- `preference-profile.json`

## Part 3: Attempt casebook

### Purpose

Build a searchable casebook from the workflow's own generated history. This is
more useful than importing community examples because each local case can retain
the exact request, references, compiled and submitted prompts, generator,
preview checks, failure categories, and later user decision.

The casebook lives in the same local browser as a separate **Attempts** view.

### One case equals one generation

Do not create one visual case per attempt file. Decision attempts can accept or
reject an earlier candidate without performing another generation.

Example:

```text
attempt 001: candidate, counts_as_generation=true
attempt 002: accepted, decision_from_attempt=1, counts_as_generation=false
```

Normalize this as one case:

```json
{
  "generation_attempt": 1,
  "decision_attempt": 2,
  "generated_status": "candidate",
  "effective_status": "accepted"
}
```

Rules:

- Candidate followed by acceptance: effective status is `accepted`.
- Candidate followed by rejection: effective status is `rejected`.
- Candidate without a decision remains `candidate`.
- Error attempts have no visual output and appear in a separate error view.
- `counts_as_generation=false` never increments generation or first-preview
  counts.
- Archived tasks are excluded by default and available only through an explicit
  filter.
- Never infer acceptance from file existence, output path, or `handoff_ready`.

### Provenance and legacy data

Prefer the immutable brief, manifest, prompt, submission, and QA snapshots inside
the attempt directory. Fall back to current task files only when an older attempt
lacks a snapshot, and label that row `legacy-fallback` or `incomplete-provenance`.

Do not manufacture missing preview checks, reference roles, user feedback, or
submission hashes for historical attempts.

### Case card

Display:

- Output thumbnail or explicit no-output state.
- Task ID and attempt number.
- Request, intent, medium, character, exact form, shot, and view.
- Generated status and effective status.
- Failure categories and user feedback.
- Compiled/submitted prompt hashes and whether they differ.
- Prompt length and compilation-report availability.
- Reference item IDs and reference count.
- Generator and timing fields.
- Identity, request, medium, and technical preview checks.
- Face/hair, fabric/fold, scene-material, and value-hierarchy checks.
- Network and retry-exhaustion state.

### Case detail

Show, when available:

- Full output.
- Ordered submitted inputs and roles.
- Compiled prompt and exact submitted prompt.
- Prompt compilation report.
- Preview checks, detailed medium checks, and full QA.
- Structured failures.
- Original and later user feedback.
- Acceptance/rejection decision chain.
- Parent and child edit/microfix relationships.

### Filters

- Effective status.
- Character and exact form.
- `new`, `edit`, or `microfix`.
- Shot and view angle.
- Failure category.
- Generator.
- Compiled/submitted prompt difference.
- Submission tracking availability.
- Reference item ID.
- Transport retry exhaustion.
- Presence of a later bounded repair.
- Legacy or incomplete provenance.

The casebook should support questions such as:

- Which human-form profile images failed identity?
- Which wide shots failed because foreground and distance had uniform detail?
- Which local edits proved zero pixel change outside the edit box?
- Which candidates still have no user decision?
- Which references recur in explicitly accepted cases?

### Read-only boundary

The casebook must not:

- Promote a case to accepted.
- Retry a generation.
- Rewrite an attempt or result.
- Automatically blame references used by a rejected image.
- Add a case to continuity authority.
- Update reference ranking or the preference profile.

Stable preference learning remains controlled by repeated explicit user feedback
through the existing preference mechanism.

## Shared gallery summary

The local browser should have three top-level views:

1. **References**: catalog items and authority-aware facets.
2. **Attempts**: normalized generation cases and effective decisions.
3. **Summary**: existing `reference_feedback_report.py` metrics, including
   status counts, failure categories, generation transport, timing coverage, and
   reference outcomes.

The Summary view is descriptive. It must not convert correlations into automatic
prompt, reference, or preference changes.

## Delivery sequence

### Phase 1: Read-only browser and casebook

- Implement `build_workflow_gallery.py`.
- Generate References, Attempts, and Summary views.
- Keep all source data read-only.
- Validate missing-image and legacy-attempt behavior.
- Verify responsive behavior in Safari and Chromium.

This phase changes no generator input and requires no visual quality claim.

### Phase 2: Explain-only prompt compiler

- Create compilation units and conflict/omission reporting.
- Add `compile_prompt.py --explain --json`.
- Keep current `prompt.md` bytes unchanged.
- Inspect real `new` tasks for semantic coverage and duplication.

This phase is compiler/audit instrumentation, not a visual promotion.

### Phase 3: Activate the `new` manga compiler

- Render `new` manga prompts from compilation units.
- Persist and hash-bind `prompt-compile.json`.
- Leave edit and microfix behavior unchanged.
- Run existing structural validation and the applicable visual A/B gates.
- Activate only after a feedback-aware promotion result passes.

### Phase 4: Optional edit and microfix adoption

Only extend the compiler if the `new` path produces measurable benefit and the
additional complexity is justified.

### Phase 5: Package and Git publication

- Review the exact live-runtime delta.
- Preview synchronization with `tools/sync_installed_skill.py`.
- Apply only explicit included files.
- Preserve package-specific configuration and unrelated dirty work.
- Commit, push, or open a pull request only when explicitly requested.

## Validation matrix

| Change | Required validation | Visual claim allowed |
| --- | --- | --- |
| Gallery/casebook only | Read-only catalog/task checks, deterministic output, browser responsive QA | No |
| Explain-only compiler | Existing tests, byte-identical prompt comparison, structured report review | No |
| Activated `new` compiler | Existing tests, compile/validation checks, real prompt diff, relevant three-case visual A/B | Only after promotion |
| Manga rendering/finish wording change | Focused manga-style visual gate in addition to applicable general gate | Only after focused promotion |
| Package synchronization | Staged sync validation, backup manifest, rollback guarantee, scoped diff review | Inherits live result; no new claim |

## Test-file policy

Do not add, modify, or expand test files unless the user explicitly authorizes
test changes in the implementation request. Existing tests may be run. Until
test changes are authorized, use the existing suite, deterministic CLI checks,
real task compilation comparisons, structural validation, and required visual
A/B runs.

## Acceptance criteria

The proposal is implemented only when all applicable criteria hold:

- No source image, historical attempt, or accepted result was rewritten.
- Gallery and casebook operate from read-only source data.
- Decision attempts do not inflate generation counts.
- Legacy gaps are disclosed rather than guessed.
- Every compiled prompt retains all required user, identity, form, topology,
  authority, and preservation constraints.
- Omitted units have deterministic, inspectable reasons.
- Generator-facing changes are not activated based only on structural checks.
- Package synchronization, commit, push, and pull-request actions remain
  separately authorized operations.
