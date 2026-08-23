# Local source authority

Use each source only for its declared role. The local catalog is a locator for a growing library, not a source of new authority.

## Source map

| Source | Path | Authority | Normal use |
| --- | --- | --- | --- |
| `official` | `/Users/jquery/Documents/inuyahsa-official` | canonical identity | Character name, face, anatomy, form, costume, weapon/prop construction and attachment, scar, and scale. |
| `manga-curated` | `/Users/jquery/Documents/inuYasha-design/origin-photos/manga-photos` | growing user-curated manga style, scene identity and scoped content | Character folders supply `character-style`; the top-level `场景/` folder supplies scene identity and scene rendering. |
| `tv-curated` | `/Users/jquery/Documents/inuYasha-design/origin-photos/TV-photos` | growing user-curated TV rendering and scoped content | TV rendering for TV tasks, or one separately selected exact-focus content reference. |
| `user-continuity` | `/Users/jquery/Documents/inuyasha-mine` | requested continuity | A user-original form or prior accepted interpretation when explicitly requested. |
| `selected-output` | `/Users/jquery/Documents/inuYasha-design/selected-output` | selected user-original precedent | One inspected accepted output for continuity and finish quality after identity and medium style are resolved. |

`official` is the default authority for that directory, not an unconditional
claim about every file. A `path_authority_overrides` entry may retain an adopted
derivative as identity evidence while labeling it `user-directed-derived-identity`.
Such an item can control the explicitly requested local variant, but it must not be described as a
publisher-original official sheet.

`official.candidate_series` is a reviewed shortlist policy, not inferred catalog
metadata. Only paths explicitly listed together may share one Top-K candidate
slot. The current request selects a member through its configured
`selection_terms`; otherwise the configured default member is used. Omit series
collapse to inspect every source file independently. Selected-medium and
continuity sources never use this policy.

Keep path casing and spelling exact. `inuyahsa-official` is the directory's existing spelling.

For both curated `origin-photos` sources, treat every folder name as inherited retrieval metadata and the leaf folder as the screenshot's content label. For `selected-output`, use its structured filenames as primary metadata and its character folders as inherited tags. All three libraries are user-owned and open-ended.

For multi-character filenames, preserve the ordered character-to-form mapping
instead of sharing one flat form list across the image. The flat list is only a
legacy union for form-only browsing; exact retrieval uses `subject_forms`.

The catalog writes `reference_domain` before ranking. `official` is `identity`;
selected-medium images under top-level `场景/` are `scene` even when a person is
visible; other selected-medium images naming a known character are
`character-style`. Never mix these domains in one relevance score.

## Default manga route

Run these layers serially. Record `HIT`, `MISS`, or `INSUFFICIENT` for the current layer before advancing; do not scan all layers in parallel.

1. Resolve every named character and required form from `official`.
2. Browse `manga-curated`, hard-filtered to `character-style`, and inspect one
   screenshot for character contour, face/hair, fabric/fold and garment values.
   Action, interaction, expression, camera and scene similarity are ignored.
3. Search `manga-curated`, hard-filtered to `scene`. For an Inuyasha-specific
   place, require its exact `scene-id`; on `MISS` or `INSUFFICIENT`, ImageGen
   constructs the scene. For a generic place, ImageGen constructs it immediately.
4. Select one scene-domain screenshot for scene rendering. An exact canonical
   scene hit may cover both steps 3 and 4 only after recording
   `scene_style_coverage=HIT` with a concrete inspection basis recorded
   consistently in evidence, brief, and manifest. Coverage `INSUFFICIENT`, or scene identity
   `MISS`/`INSUFFICIENT`, requires a separate scene-style reference and the
   fallback query excludes the canonical `scene-id` already judged inadequate.
5. If the request needs separately evidenced non-scene content, search `manga-curated` for
   that exact content. Only after a recorded `MISS` or `INSUFFICIENT`, search
   `tv-curated` and select at most one image as `content` with a non-empty focus.
6. Search `selected-output` only when accepted continuity was explicitly requested.
   Inspect at most one matching precedent. A `MISS` here is allowed.
7. Let ImageGen design the new composition, pose, action, expression and staging.

Do not use a manga screenshot or selected output as identity evidence. Do not copy a screenshot's panels, dialogue, depicted characters, or story. Do not let selected output replace the selected medium's original rendering evidence.

A TV fallback in a manga task is not manga style evidence. It may control only
the named visible content. Ignore its color, animation contour, cel shadow,
background treatment, framing, and character rendering, and translate the focus
through the separately selected manga style reference.

## Manga edit and microfix route

For an edit, put the user target first and preserve every unrequested region. Add no more than one manga screenshot and only the official sheets needed by the changed category.

If the needed official evidence is a small sub-view inside a multi-view sheet,
prepare one task-local crop with recorded coordinates and exact focus. The crop
remains official evidence; it does not become a user target or a composition
reference.

For a microfix, inherit the validated parent evidence instead of restarting the default manga route. Use target plus official identity evidence for identity, form, costume, or anatomy; target plus one manga screenshot for medium or tone; otherwise use target-only unless the user supplies a distinct reference. Do not add selected-output continuity when the target already provides exact continuity.

## Default TV route

1. Resolve identity from `official`.
2. Browse and inspect one `tv-curated` screenshot for palette and TV rendering.
3. When separate content evidence is needed, search `tv-curated` first; after a
   recorded miss or insufficiency, permit one exact-focus `manga-curated` content
   fallback with all manga rendering authority removed.
4. Search `selected-output` for the same subject and form only when continuity is requested.
5. Design the new composition in the prompt.

Do not use manga screenshots or selected-output images as TV style evidence.

## Conflict priority

1. A user-provided target controls an edit's exact instance.
2. Explicitly requested user continuity controls the user's established variant.
3. Official sheets control canonical identity and construction.
4. Selected `manga-curated` screenshots control manga mark-making only.
5. A selected `tv-curated` screenshot controls TV rendering only.
6. One separately selected `content` reference controls only its exact declared focus.
7. `selected-output` controls accepted continuity and finish quality only.
8. The request and prompt control new composition and story content.

Append-only attempt outcomes and learned preference traits may rank otherwise valid candidates, but they never outrank these authority rules or relax form compatibility.

When sources show incompatible forms, costumes, ages, or media, name the chosen branch. Never silently average them.

If a design is genuinely anime-original rather than merely absent from the local
manga curation, label the task as a TV-derived design translated into manga
rendering with `content_need.provenance: fallback-medium-original`. Do not
describe it as an original-manga canonical form. If the request
requires manga-only canon, report the missing manga evidence instead of silently
substituting the TV design.
