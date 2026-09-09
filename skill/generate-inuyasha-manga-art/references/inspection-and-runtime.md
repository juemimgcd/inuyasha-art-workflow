# Construction evidence and runtime provenance

Set `INUYASHA_SKILL_DIR` to the installed skill directory before using the
commands below. On Windows, use its `scripts/run-python.ps1` launcher.

These tools strengthen inspection, handoff, and reproducibility. They do not
modify generator prompts, primary retrieval ranking, selected inputs, or the
rendering map. A generator-facing change still needs the existing visual A/B
promotion gate. Passing an audit is not evidence of improved image generation.

## Shot-specific construction review

For a new character image, or an identity/form/costume/anatomy/construction edit,
prepare a review after inspecting the generated output and before recording a
candidate. Continue to use the existing prompt path unchanged.

```bash
"$INUYASHA_SKILL_DIR/scripts/run-python" \
  "$INUYASHA_SKILL_DIR/scripts/structure_review.py" prepare \
  --task-dir <task> --output <generated-image>
```

The pending `structure-review.json` is derived from the task's subject/form and
shot-specific official facets. Complete each row from visible source and output
regions. `expected` should name the actual relationship, such as which collar
layer overlaps which, where the tie attaches, or which sleeve opening is visible.
Do not replace construction with a generic claim such as “costume correct.”

- `visibility=visible`: supply `expected`, selected `reference_item_id`, its
  `reference_sha256`, `reference_box`, `output_box`, `result=pass|fail`, and a
  concrete `note`. Boxes are integer `[x,y,width,height]` in the respective files.
- `visibility=not-visible`: use `result=n/a` and explain the actual crop,
  occlusion, or shot scale. Do not force hidden knots, feet, or accessories into
  the drawing. A partially visible facet still needs visible-region inspection;
  its note must distinguish inspected construction from hidden parts.
- Official identity evidence controls canonical structure. An unchanged edit
  target can provide instance-specific structure. Style images cannot become
  construction authority; a form-only fallback remains limited to form state.
- Keep expectations specific to this shot. Simplifying fold marks does not
  authorize removing a visible collar layer, tie, opening, or attachment.

Run `structure_review.py check --task-dir <task> --output <image>` after filling
the review. `record_attempt.py` automatically checks the task's default review;
use `--structure-review <path>` for an explicitly named review. Failed, pending,
missing-facet, stale-hash, and out-of-bounds reviews block candidate/accepted
handoff. Rejected outputs remain recordable. The review is copied into the
immutable attempt, inherited by a later decision, and rechecked at final
validation. Historical attempts without this sidecar keep their existing rules.
Prepare a separate review path for another output; never rewrite an attempt's
review or treat this audit as user acceptance.

## Reusable inspected reference regions

After actually viewing a selected reference, store one useful visible detail:

```bash
"$INUYASHA_SKILL_DIR/scripts/run-python" \
  "$INUYASHA_SKILL_DIR/scripts/reference_observations.py" record \
  --task-dir <task> --item-id <selected-item> --scope construction \
  --region X,Y,WIDTH,HEIGHT --subject-form 戈薇=default-form \
  --view-angle three-quarter-front --detail "<observed layer relationship>" \
  --tag 领口
```

Records live under the workflow root's `reference-observations/`, separately
from source images and catalog ranking. They bind original and rendered bytes,
the inspected region, authority, visible subject/form, and view. Multi-subject
references require explicit visible subject/form entries for the actual region.
This avoids crediting an unseen co-character merely because the page contains it.

For a detail-coverage diagnosis, search these inspected observations:

```bash
"$INUYASHA_SKILL_DIR/scripts/run-python" \
  "$INUYASHA_SKILL_DIR/scripts/reference_observations.py" search \
  --scope construction --subject-form 戈薇=default-form --detail 领口 \
  --view-angle three-quarter-front
```

Search supports `construction`, `form`, `character-rendering`, and
`scene-rendering`. Rendering search keeps the selected medium. Results group
coverage by requested subject, with at most four records per group, so separate
character anchors can be inspected without demanding one interaction image.
`INSUFFICIENT_VIEW` identifies a detail match whose inspected view is unsuitable;
`MISS` means no matching inspected observation, not an empty source library.
Changed images, metadata, or observation bytes invalidate their evidence.

This is a search of accumulated visual notes, not automatic image understanding.
Use it to locate evidence and diagnose gaps within the existing bounded
inspection. It neither executes another primary retrieval nor changes selection
automatically. Inspect the suggested region against the current request before
using it. Preserve exact character/form/medium rules and record insufficiency
when coverage remains absent. Do not infer new pose or composition authority.

## Protected regions in full-canvas edits

Keep crop-and-composite for a safely bounded change. For silhouette, perspective,
or pose changes crossing the crop boundary, use the existing explicit
`--full-canvas` child edit. In that output's structure review, protected areas can
be declared as `protected_regions: [{"name":"left background","box":[0,0,200,800]}]`.
Set `protected_target_sha256` to the original target hash.

The review requires unchanged dimensions and exact RGBA pixel equality in every
declared protected box, including fully transparent pixels. A failure blocks
candidate handoff. This proves preservation only in those regions; it does not
prove the entire full-canvas edit stayed unchanged. Declare meaningful unchanged
areas from the user's edit scope, and inspect the remaining unchanged structure.

## Runtime inventory and upgrade planning

`prepare_generation_submission.py` now snapshots the actual installed-file
fingerprint, configuration hash, comparison revision, and any unrecorded drift.
Existing attempt/submission hashes preserve that runtime record with each call.

After reviewed maintenance, run:

```bash
"$INUYASHA_SKILL_DIR/scripts/run-python" \
  "$INUYASHA_SKILL_DIR/scripts/runtime_provenance.py" record \
  --source-repo <package-checkout> --revision <commit>
```

`status` recomputes installed bytes. `plan-upgrade --source-repo <repo>
--revision <commit>` compares the recorded source, actual installation, and
incoming committed files without writing them. It distinguishes upstream
updates/removals, local edits, conflicts, and pre-existing differences requiring
review. The machine-specific `references/source-library.json` is protected and
hashed separately. Tests are inventoried for reproducibility; this tool does not
modify them.

`.runtime-provenance.json` records an inventory, not a fabricated installation
history. A mixed installation reports `source_revision=null`, the explicit
`comparison_revision`, and differences of unknown origin until reviewed. Old
records are retained in `.runtime-history/`. Review and stage named changes with
backup and validation before installing; a conflict is never an overwrite plan.
Repository packaging still uses the existing explicit sync tool and scope.
