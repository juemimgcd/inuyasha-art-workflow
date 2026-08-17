# Prompt recipes

Adapt these structures; do not paste every option into every prompt.

Use `compile_prompt.py` for the base prompt. Append only the scene-specific recipe clauses that add observable information. Do not duplicate the base authority, identity, no-text, or preservation clauses.

Choose recipes from the selected medium. Do not append manga rendering clauses to a TV prompt or TV color/cel-shading clauses to a manga prompt.

When a manga style-reference image is actually present, state before the scene
specification: `Each manga style-reference image controls mark-making only. Use
its declared line hierarchy, black-white balance, halftone economy, or effect
construction; ignore and do not reproduce its characters, dialogue, balloons,
panel borders, layout, or story.` Do not add a style image merely because a
recipe exists, and never select one by a fixed volume or page. Let official
setting sheets control named-character identity. Design the requested composition
anew unless the user supplied a target or original panel.

When a separately declared `content` image comes from the non-selected medium,
state its exact focus once and translate only that visible fact. Explicitly ignore
the source medium's palette, contour grammar, shading, texture, background,
framing, and character rendering. Never append the non-selected medium's style
recipe merely because its content image is attached.

## Contents

- [Standalone character illustration](#standalone-character-illustration)
- [Quiet dialogue page](#quiet-dialogue-page)
- [Emotional close-up](#emotional-close-up)
- [Combat impact](#combat-impact)
- [Monster reveal](#monster-reveal)
- [Atmospheric establishing shot](#atmospheric-establishing-shot)
- [TV standalone character illustration](#tv-standalone-character-illustration)
- [TV action frame](#tv-action-frame)
- [Character continuity pass](#character-continuity-pass)
- [Revision prompts](#revision-prompts)

## Standalone character illustration

```text
[Character] at [specific emotional/action moment] in [setting]. Vertical [shot size] from [camera angle], with [primary silhouette or prop] forming the focal shape and generous negative space around the face. Classic black-and-white supernatural manga print: flexible tapered dip-pen contours, outer silhouette heavier than facial lines, clean white skin, [black or white] hair mass with narrow highlight channels, broad period-garment folds. Limit shading to one light and one middle dot screen; reserve pure black for [hair/night/effect]. Add [wind/mist/foliage] with sparse pen textures. Crisp readable silhouette, text-free, no speech balloons. Avoid glossy anime rendering, painterly grayscale, photorealism, uniform vector lines, and dense gray everywhere.
```

## Quiet dialogue page

```text
A complete monochrome manga page with [5-7] panels and [right-to-left or left-to-right] reading order. Scene: [brief beat-by-beat action]. Begin with one location-establishing panel, alternate horizontal reaction strips and compact two-shots, and end on one larger emotional close-up. Use economical oval faces, emphasized upper eyelids, tiny nose marks, small mouths, black hair masses, flexible tapered ink, clean white skin, and restrained dot screens. Simplify backgrounds after the establishing panel. Reserve clear white speech-balloon spaces but leave them blank. Use a black field or stippled halo only at the emotional turn. No generated lettering, no cinematic grayscale painting, no uniform six-card grid.
```

## Emotional close-up

```text
Close-up of [character] realizing [emotion or revelation], face turned [direction], eyes focused on [off-frame subject]. Keep the face mostly white with a strong upper eyelid, one or two eye highlights, a tiny nose wedge, and a restrained mouth. Frame the hair as [solid black / mostly white] with tapered locks. Let the background fall into [white negative space / black-to-stipple vignette / soft dot cloud]. Use only a few stress hatches, one sweat drop, or a small blush tone. Quiet black-and-white manga ink, intimate and readable, no realistic skin rendering, no glossy anime eyes, no text.
```

## Combat impact

```text
Freeze the exact instant when [attacker] strikes [target] with [weapon/energy]. Use a low or tilted camera and one dominant diagonal from [origin] to [impact]. Crop [weapon, sleeve, enemy limb, debris] at the frame edges. Build the impact from a white core, black wedges, a few flying fragments, and converging speed-line bundles. Let clothing and hair trail opposite the attack direction. Use bold tapered black effect shapes as abstract graphics, not readable lettering. Keep the fighters' silhouettes distinct; use at most two halftone densities. Enforce one dense texture zone only: if the target is textured, reduce architecture and foliage to clean contours or silhouette, keep skin white, and give each garment one tone at most. Late-action black-and-white manga print, sharp but organic pen contours. Avoid 3D lighting, motion blur, gray fog over the whole image, material rendering on every surface, and random lines with no vanishing point.
```

## Monster reveal

```text
A supernatural monster emerges from [place], towering over [small human figure or environmental scale cue]. Base the anatomy on [animal/insect/plant/mask/bone] and distort [one or two defining traits]: [asymmetry, layered mouth, swollen eyes, segmented limbs, tendrils, exposed bone]. Compose a large readable silhouette against [white mist / black night / simple shrine architecture]. Render flesh or shell with contour bands, sparse hatching, stipple, and flat black cavities; contrast the grotesque texture with the protagonist's clean face. Use a low-angle reveal, one foreground obstruction, and restrained halftone. No photoreal creature rendering, no generic game-concept-art armor, no color unless requested.
```

## Atmospheric establishing shot

```text
Wide establishing view of [shrine/village/forest/field/ruin/modern street] at [time/weather], with [characters] small in the frame. Organize the view into a dark foreground silhouette, a lightly toned middle ground, and a mostly white or black sky. Use credible perspective, clustered foliage, parallel pen strokes for wood/stone/soil, and one supernatural interruption such as [mist trail, white moon, distant aura]. Black-and-white manga print with large simple value masses; no photographic texture, no full grayscale painting, no excessive detail competing with the figures.
```

## TV standalone character illustration

```text
[Character] at [specific emotional/action moment] in [setting]. Compose a [shot size] from [camera angle], with [primary silhouette or prop] as the focal shape. Color TV-anime frame grounded in the selected TV screenshot: clean economical contours, stable official face and costume construction, flat canonical local colors, one hard-edged cel-shadow family, restrained highlights on [hair/eyes/metal/effect], and a simplified painted background softer than the character. Preserve [identity anchors] exactly. No manga halftone, printed-paper texture, dry-brush ink, photoreal materials, soft airbrush skin, glossy 3D lighting, or text.
```

## TV action frame

```text
Freeze the exact TV-animation instant when [attacker] [action] toward [target]. Preserve one dominant body/weapon diagonal, clear screen direction, readable silhouettes, and the episode-grounded palette. Use clean contour animation drawing, flat local colors, one hard-edged shadow family, restrained motion streaks, a compact impact flash, and a simplified painted background. Keep ears, hair, hands, weapon proportions, costume layers, and facial markers unobstructed. No panel borders, halftone, manga speed-line field, painterly rendering, bloom-heavy game art, or uncontrolled gradients.
```

## Character continuity pass

Append this block when generating a batch:

```text
Canonical identity ledger from the inspected official setting sheets: [canonical character name] | [age/form] | [hair and head silhouette] | [face markers] | [garment layers and pattern] | [weapon or prop proportions] | [relative height]. Maintain every listed marker across the set. Vary camera and gesture, not identity. Do not borrow features from [named high-risk confusion character]. Keep the selected visual mode [early-rounded / classic-balanced / late-action] unchanged throughout.
```

For TV mode, replace the manga period-mode clause with: `Keep the selected TV palette, cel-shadow depth, line economy, and background treatment unchanged throughout.` For multiple named characters, write one ledger line per character before the scene description. Never rely on names alone to bind appearances.

## Revision prompts

For a microfix, keep the complete prompt under 1,800 characters. Name one failure category, state the visible change, and list the already-passed invariants to preserve. Do not repeat the complete new-image recipe.

### Manga result looks like modern anime

```text
Redraw as printed black-and-white manga made with flexible dip-pen ink. Remove glossy cel shading, bloom, lens effects, and smooth digital gradients. Make outer contours heavier than facial lines, keep skin white, replace soft gray rendering with one light and one middle dot screen, and simplify the face.
```

### TV result looks like colorized manga or glossy key art

```text
Redraw as a production TV-anime frame. Remove halftone, printed-paper texture, dry-brush ink, glossy 3D lighting, bloom, and painterly gradients. Use clean economical contours, flat canonical colors from the selected TV reference, one hard-edged cel-shadow family, restrained highlights, and a simplified painted background.
```

### Result is muddy

```text
Increase black-white separation. Clear halftone from skin and focal edges, merge small dark details into larger black masses, preserve one mid-gray garment tone, and leave at least one third of the composition as clean white negative space.
```

### Result is over-rendered

```text
Redraw with a strict manga simplification budget while preserving the pose and composition. Keep only one dense texture zone. Remove material rendering from distant architecture, foliage, rubble, fabric, and skin; convert them to clean contours, sparse tapered strokes, or flat silhouettes. Use one tone per garment, keep skin white, and leave at least one third of the image as untouched white paper.
```

### Action lacks force

```text
Recompose around one dominant diagonal and one impact center. Enlarge the attacking silhouette, crop foreground forms, align speed lines to the strike, add a white impact core with black wedges and debris, and remove unrelated motion marks.
```

### Prop floats or intersects clothing

```text
Redraw only the attachment and overlap structure. Trace one continuous support chain from [belt/strap/hand] through [mount/guard] to [prop or sheath]. Keep all connected parts on one axis with coherent near/far size change and gravity direction. State the occlusion order explicitly: [inner layer] behind [mount], [outer garment] in front of [upper section], [lower section] outside the body silhouette. Remove every contour that passes through hair, fur, clothing, or limbs, and preserve all unrelated pixels.
```

### Face is too realistic

```text
Simplify the face to a compact manga oval with a short chin, emphasized upper eyelids, one or two eye highlights, a tiny nose mark, a small geometric mouth, and no modeled lips, nostrils, pores, or 3D cheek shading.
```
