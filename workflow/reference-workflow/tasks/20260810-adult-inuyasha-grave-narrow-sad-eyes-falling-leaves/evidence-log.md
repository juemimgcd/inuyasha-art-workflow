# Evidence log

Task: `20260810-adult-inuyasha-grave-narrow-sad-eyes-falling-leaves`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: No additional identity reference; the supplied edit target already establishes adult half-demon Inuyasha.
- Source searched: User-supplied target image.
- Result: HIT
- Selected item IDs: user-supplied:file:e991a27c7f9a75e05fd3
- Usable evidence: White hair, dog ears, face, beads, robe, sword, body proportions, pose, and every unchanged region.

## Layer 2: Manga or TV screenshots

- Need: No additional rendering reference; the target already provides the black-and-white manga grammar.
- Source browsed: User-supplied target image.
- Selected item IDs: user-supplied:file:e991a27c7f9a75e05fd3
- Result: HIT
- Controls: Existing linework, screentone, composition, scenery, and treatment of the added leaves.
- Must not control: Nothing outside the user-requested eye-expression and falling-leaf edit may change.

## Layer 3: exact content evidence

- Need: N/A
- Query: N/A
- Selected-medium source: manga-curated
- Selected-medium result: SKIP
- Cross-medium fallback source: tv-curated
- Cross-medium fallback result: SKIP
- Selected item IDs: N/A
- Exact focus: N/A
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP` unless continuity was requested
- Selected item IDs: N/A
- Usable evidence: N/A
