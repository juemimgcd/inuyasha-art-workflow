# Visual trait annotations

Annotate only distinctions that filenames and folders cannot express. Keep identity
and form in structured filenames; use scoped identity facets for official setting
sheets and rendering traits to rank inspected manga screenshots and accepted outputs.

Allowed trait keys:

- `style-anchor`: `certified` — manually inspected for a specific, reusable
  rendering relationship; this is only a same-score tie-breaker and never adds
  identity, content, composition, or scene authority
- `scene-class`: `canonical`, `generic`
- `scene-id`: `bone-eaters-well`, `goshinboku`
- `scene-family`: `architecture`, `nature`, `settlement`, `interior`, `canonical-landmark`
- `scene-structure`: `overall`, `detail`, `spatial-relation`
- `action`: `embrace`, `embrace-from-behind`, `look-down`, `look-up`, `reach`, `hold`, `cut`, `turn-head`, `sleeve-hidden-hands`, `face-off`, `draw-weapon`, `sheath-weapon`, `swing-weapon`, `activate-wind-tunnel`, `ride`, `fly`, `transform`, `conjure`, `fall`, `jump`, `run`, `sit`, `kneel`, `carry`, `crouch`, `pass-ball`, `catch-ball`, `kick-ball`, `comb-hair`, `touch-ears`, `adjust-clothing`
- `interaction`: `mother-child`, `romantic`, `face-to-face`, `body-contact`, `hand-prop`, `hand-clothing`, `shoulder-rest`, `shared-gaze`, `confrontation`, `caregiving`, `teaching`, `ear-touch`, `rider-mount`, `scale-reference`
- `expression`: `alert-sad`, `shy`, `surprised`, `gentle`, `restrained`, `angry`, `determined`, `crying`, `neutral`
- `content-object`: `knife`, `daikon`, `grave`, `tessaiga`, `tenseiga`, `ball`, `shopping-bag`, `bow`, `well`, `tree`, `comb`, `mirror`, `hair-ribbon`, `robe-sleeve`, `shrine`, `beads-of-subjugation`, `staff`, `prayer-beads`, `wind-tunnel-seal`, `hiraikotsu`, `arrow`, `quiver`, `backpack`, `medical-kit`, `sword`, `staff-of-two-heads`, `hammer`, `harness`, `fan`, `feather`, `horse`, `mask`, `eyepatch`, `travel-pack`, `walking-stick`, `spear`
- `scene-energy`: `quiet`, `dialogue`, `action`, `impact`
- `face-clarity`: `low`, `medium`, `high`
- `line-weight`: `soft-variable`, `firm-variable`, `heavy-action`
- `tone-density`: `light`, `balanced`, `dense`
- `black-mass`: `hair-dominant`, `effect-dominant`, `background-dominant`, `balanced`
- `background`: `minimal`, `nature`, `architecture`, `night`, `interior`, `courtyard`, `shrine`, `graveyard`
- `effect-type`: `none`, `wind`, `rain`, `mist`, `snow`, `snow-light`, `snow-heavy`, `speed-lines`, `impact`, `aura`, `wind-tunnel`, `fox-fire`, `transformation`
- `suitable-for`: `close-up`, `two-shot`, `full-body`, `back-view`, `quiet-scene`, `combat`, `establishing`, `weapon-mount`, `weapon-construction`, `garment-overlap`, `footwear`, `ground-contact`
- `view-angle`: `front`, `three-quarter-front`, `profile`, `three-quarter-back`, `back`, `high-angle`, `low-angle`, `multi-view`
- `depth-layout`: `same-plane`, `foreground-midground`, `foreground-background`, `layered`
- `occlusion`: `clear`, `partial`, `heavy`, `body-body`, `garment-body`, `garment-prop`
- `contact-type`: `none`, `ground`, `body`, `prop`, `clothing`
- `prop-attachment`: `none`, `waist`, `back`, `hand`, `shoulder`, `clothing`, `body`
- `costume-state`: `without-fire-rat-robe`
- `perspective-risk`: `low`, `medium`, `high`
- `scene-economy`: `authored-negative-space`, `selective-detail`, `dense-functional`
- `detail-falloff`: `strong`, `moderate`, `flat`

Official identity construction also uses exact subject-scoped tags of the form
`identity-facet:SUBJECT:FORM:FACET`. Supported facets are `face`, `hair-ear`,
`costume`, `garment-overlap`, `hands`, `feet`, `prop-attachment`, and
`construction`. Single-subject/single-form pages may derive unambiguous facets
from their existing shot and construction tags; use a scoped tag for
multi-character or multi-form pages so one subject's hand, foot, or weapon does
not leak to another. Add one with:

```bash
scripts/run-python scripts/annotate_reference.py \
  --item-id official:file:... \
  --identity-facet '铁碎牙=transformed-form:construction'
```

Example:

```bash
scripts/run-python scripts/annotate_reference.py \
  --item-id manga-curated:file:... \
  --trait style-anchor=certified \
  --trait action=embrace \
  --trait interaction=body-contact \
  --trait scene-energy=quiet \
  --trait face-clarity=high \
  --trait tone-density=light \
  --trait view-angle=back \
  --trait prop-attachment=waist
```

Rebuild the catalog after annotation. Search with `--query "scene-energy:quiet face-clarity:high"` when the trait is relevant. Do not annotate every file merely to fill fields.

Certify only a small inspected set. A certified character anchor still applies
only to its visible shot, face/hair, fabric/fold, and value relationships; a
certified scene anchor still applies only to its visible materials, weather,
negative space, black-white mass, and depth falloff. Certification never makes
the image a fixed prompt input, and an exact request/shot/material match remains
more important than the certification tie-breaker.

`scene-id` is an exact identity key for a work-specific canonical place. Search it
inside `reference_domain=scene` before asking ImageGen to construct the scene.
Generic places use scene-family, background, effect and rendering traits instead.

For natural-language requests, use `--intent-text`. It maps only explicit phrases
such as `背后拥抱`, `蹲坐抱球`, `袖中藏手`, `挥动铁碎牙`, or `雨夜神社` to
controlled traits and uses them as ranking hints. It does not hard-filter the
catalog, grant a source new authority, or automatically require content evidence.
An explicit `wide-shot` also contributes `scene-economy:authored-negative-space`
and `detail-falloff:strong`; these are observable rendering traits, not names of
past failures or fixed reference IDs.

Trait keys and values are controlled; `annotate_reference.py` rejects typos or
unsupported values. During rebuild, `view-angle:back` and
`suitable-for:back-view` also add the structured `back-view` shot facet, while
`suitable-for:close-up`, `two-shot`, `full-body`, and `establishing` promote to
their corresponding shot facets.
