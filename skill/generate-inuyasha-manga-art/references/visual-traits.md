# Visual trait annotations

Annotate only distinctions that filenames and folders cannot express. Keep identity and form in structured filenames; use these traits to rank inspected manga screenshots and accepted outputs.

Allowed trait keys:

- `scene-energy`: `quiet`, `dialogue`, `action`, `impact`
- `face-clarity`: `low`, `medium`, `high`
- `line-weight`: `soft-variable`, `firm-variable`, `heavy-action`
- `tone-density`: `light`, `balanced`, `dense`
- `black-mass`: `hair-dominant`, `effect-dominant`, `background-dominant`, `balanced`
- `background`: `minimal`, `nature`, `architecture`, `night`, `interior`
- `effect-type`: `none`, `wind`, `rain`, `mist`, `speed-lines`, `impact`, `aura`
- `suitable-for`: `close-up`, `two-shot`, `full-body`, `back-view`, `quiet-scene`, `combat`, `establishing`, `weapon-mount`, `garment-overlap`, `footwear`, `ground-contact`
- `view-angle`: `front`, `three-quarter-front`, `profile`, `three-quarter-back`, `back`, `high-angle`, `low-angle`, `multi-view`
- `depth-layout`: `same-plane`, `foreground-midground`, `foreground-background`, `layered`
- `occlusion`: `clear`, `partial`, `heavy`, `body-body`, `garment-body`, `garment-prop`
- `contact-type`: `none`, `ground`, `body`, `prop`, `clothing`
- `prop-attachment`: `none`, `waist`, `back`, `hand`, `shoulder`, `clothing`
- `perspective-risk`: `low`, `medium`, `high`

Example:

```bash
scripts/run-python scripts/annotate_reference.py \
  --item-id manga-curated:file:... \
  --trait scene-energy=quiet \
  --trait face-clarity=high \
  --trait tone-density=light \
  --trait view-angle=back \
  --trait prop-attachment=waist
```

Rebuild the catalog after annotation. Search with `--query "scene-energy:quiet face-clarity:high"` when the trait is relevant. Do not annotate every file merely to fill fields.

Trait keys and values are controlled; `annotate_reference.py` rejects typos or
unsupported values. During rebuild, `view-angle:back` and
`suitable-for:back-view` also add the structured `back-view` shot facet, while
`suitable-for:close-up`, `two-shot`, `full-body`, and `establishing` promote to
their corresponding shot facets.
