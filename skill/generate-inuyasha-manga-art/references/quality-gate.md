# Output quality gate

Run the applicable checks at full image size. Mark every item `pass`, `fail`, or `n/a` in the task's `qa.json`. Revise one failed category at a time and repeat all invariants.

Before generating a revision, record the rejected candidate with `record_attempt.py` and a structured failure category. Do not overwrite the rejected prompt, manifest, QA, or output record. For microfix tasks, also verify that every non-target region remains unchanged in composition and identity. For crop-and-composite microfixes, run `composite_local_microfix.py` first and require exact pixel equality outside the declared `edit_box`.

Before handing off a first preview, record exactly four blocking checks:
`identity`, `request`, `medium`, and `technical`. Every result must be `pass`.
Each pass must state the concrete visible evidence used for that judgment.
This is smaller than full acceptance QA but is not optional; `candidate` is
reserved for a visually usable preview. Any failed blocking check requires a
`rejected` attempt with the corresponding structured failure category.

## Contents

- [Six acceptance dimensions](#six-acceptance-dimensions)
- [Identity](#identity)
- [Medium](#medium)
- [Composition](#composition)
- [Construction](#construction)
- [Technical integrity](#technical-integrity)
- [Revision order](#revision-order)

## Six acceptance dimensions

For every new split-domain image, record all six dimensions in `qa.json`. Each
must be `pass` with a concrete inspection note before `record_attempt.py
--status accepted` is allowed:

1. `character_identity`: official character, form, costume and canonical marks.
2. `character_style`: character linework, face/hair simplification, fabric/fold
   treatment and garment value hierarchy from the character-style input only.
3. `scene_identity`: canonical structure when applicable, or faithful ImageGen
   construction of the requested generic scene.
4. `scene_style`: materials, weather, black-white mass, negative space and
   distance falloff from valid scene-domain evidence.
5. `action_request`: requested pose, action, expression, interaction and exact
   moment are present without being copied from references.
6. `composition_integration`: characters and scene share one camera, perspective,
   scale, occlusion, contact system and focal hierarchy.

A single `fail` or `pending` dimension blocks acceptance. Do not average a failed
identity or scene result into an overall aesthetic score. The list must contain
exactly these six unique IDs; an extra or duplicate row is invalid and cannot
override an earlier failure.

## Identity

- Check identity and form before judging medium economy. Simplification never
  excuses a generic face, lost bang structure, altered jaw, collapsed hair
  silhouette, or missing costume layer.
- Match every focal character to the recorded canonical name, age or form, hair and head silhouette, face markers, garment layers, weapon or prop, and relative scale.
- Keep high-risk pairs distinct: 戈薇/桔梗, 神乐/神无, 幼年枫/枫婆婆, 犬夜叉/杀生丸, 七宝/云母, 云母/哞哞.
- Reject incompatible form or costume merges.
- Check hands, ears, jewelry, weapons, layered clothing, and transformation markers at full size.

## Medium

### Manga

- Require the first impression to be an economical late-1990s serialized manga
  image in the selected style reference's scene-appropriate density band, not a
  polished monochrome illustration or an under-rendered coloring-book outline.
  Reject strand-by-strand hair, abundant tiny folds, delicate micro-texture,
  smooth volume shading, glossy finish, or uniformly perfected digital contours.
  Also reject generic anime faces, uniform vector contours, empty architecture,
  missing garment construction, or missing interaction/contact cues. Clean and
  controlled is good; neither extra refinement nor extra sparsity is
  automatically more faithful.
- For a requested manga-medium correction, reject a result that only desaturates,
  removes smooth gray, or substitutes screen tone while preserving the target's
  over-finished surfaces. Also reject a correction that removes identity-bearing
  eyes, bangs, jaw, hair silhouette, costume layers, hand contact, or necessary
  setting cues. Require movement toward the selected style reference's density
  band, not a one-way reduction in mark count.
- Reject generator-only numeric caps or percentage reductions for strands,
  folds, tones, rain lines, or background marks unless the selected style
  reference itself makes that relationship observable.
- Reject colored-anime rendering merely converted to grayscale.
- When a selected curated style screenshot is present, confirm that it influenced
  mark-making only; reject copied source characters, dialogue, balloons, panel
  borders, layout, or story content.
- When a TV screenshot is present as manga `content`, confirm that only its exact
  declared focus survived. Reject TV palette translated to grayscale, uniform
  animation contours, cel-shadow shapes, anime facial construction, copied
  framing, or background treatment.
- Keep skin and focal edges clean; do not blanket every surface with halftone.
- Use variable organic line hierarchy rather than uniform vector-clean or uncontrolled scratchy lines.
- Let dense texture and tone follow the selected evidence and narrative focus;
  keep them subordinate to faces and action readability rather than enforcing a
  universal count.
- For a manga `wide-shot`, require large silhouettes, genuine untouched paper,
  decisive flat black, a restrained middle-tone family, and visible detail
  falloff with distance. Reject leaf-by-leaf foliage, repeated roof-tile or
  wood-grain rendering, all-over rock strata, and distant objects finished with
  the same precision as the foreground. Correct perspective does not excuse a
  monochrome concept-art, engraving, or etching finish.

### TV

- Reject colorized manga, glossy game key art, soft airbrush skin, and 3D material lighting.
- Use clean economical contours, stable flat local colors, one main hard-edged cel-shadow family, and restrained highlights.
- Keep the selected screenshot palette and background treatment dominant.
- When a manga panel is present as TV `content`, confirm that its ink hierarchy,
  halftone, print texture, panel framing, and manga facial construction did not
  leak into the TV rendering.

## Composition

- Give the image one obvious focal hierarchy.
- For action, require one dominant direction, a readable silhouette, and a clear impact center.
- Keep the background less detailed than the focal character.
- When the environment itself is focal, compare surface finish against narrative
  function instead: major axes, silhouette, scale, route, overlap, and ground
  contact must be clear, while repeated construction and material micro-texture
  are omitted. Large unrendered paper areas are allowed and expected.
- Keep panels, balloons, effects, and foreground crops from obscuring identity-critical shapes unintentionally.

## Construction

- Use one coherent depth system for characters, props, ground, and background; reject conflicting scale, horizon, or foreshortening cues.
- Trace every support or contact chain continuously: body to ground, hand to prop, belt or mount to sheath, limb to clothing, and interacting body to body.
- Make the occlusion order unambiguous. Reject contours that pass through hair, fur, sleeves, robes, limbs, weapons, or scenery without a visible front/behind relationship.
- For worn equipment, verify attachment point, gravity direction, shared axis, near/far size change, and the clothing layer that covers or supports it.
- Inspect feet, seated weight, leaning bodies, and pinned or restrained poses for credible contact rather than floating.

## Technical integrity

- Render no unrequested lettering, speech bubbles, logos, signatures, or watermarks.
- Preserve the requested aspect ratio and deliverable type.
- Verify that every file in `reference-manifest.json` was actually inspected and used only for its declared role.
- Verify that the official sheets, not the manga style screenshots, controlled named-character identity.
- Verify that no non-selected medium received style authority.
- For every `content` entry, verify one non-empty exact focus, at most one content
  image, and no influence outside the named action, object/creature state, effect
  phase, or necessary spatial relationship.
- For cross-medium content, verify that the selected-medium search recorded
  `MISS` or `INSUFFICIENT` before the fallback `HIT`, and that the prompt names
  the conversion direction without presenting the source as selected-medium canon.
- For crop-and-composite microfixes, verify the sidecar report exists, the output canvas matches the source dimensions, and `outside_edit_box_preserved` is true.

## Revision order

Fix failures in this order:

1. identity or form
2. medium leakage
3. hand, weapon, and costume integrity
4. attachment, overlap, perspective, and ground contact
5. composition and action clarity
6. background and texture economy
7. minor polish

Do not rewrite the whole prompt when one category fails. State `change only <failed category>; keep <all passed invariants> unchanged`.

After the user accepts an output, record the accepted attempt and only the preferences the user explicitly confirmed. Do not infer general taste from silent acceptance or from a file being copied into an output directory.
