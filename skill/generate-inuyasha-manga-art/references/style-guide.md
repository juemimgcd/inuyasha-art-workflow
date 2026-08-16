# Visual system extracted from the local manga corpus

## Contents

- [Evidence base](#evidence-base)
- [Core manga impression](#core-manga-impression)
- [Visual hierarchy](#visual-hierarchy)
- [Ink and contour](#ink-and-contour)
- [Faces and bodies](#faces-and-bodies)
- [Hair, fabric, costume, and fur](#hair-fabric-costume-and-fur)
- [Halftone and texture](#halftone-and-texture)
- [Quiet storytelling](#quiet-storytelling)
- [Action construction](#action-construction)
- [Monsters and supernatural effects](#monsters-and-supernatural-effects)
- [Backgrounds and setting](#backgrounds-and-setting)
- [Period modes](#period-modes)
- [Color exception](#color-exception)
- [Failure patterns to prevent](#failure-patterns-to-prevent)

## Evidence base

This guide was derived from the user's 30 local PDF volumes (`Qyc-Hhb Vol.01.pdf` through `Qyc-Hhb Vol.30.pdf`), about 10,600 pages in total. The initial pass sampled early, middle, and late pages from every volume, then inspected selected pages at higher resolution for facial construction, line taper, tones, backgrounds, effects, and monster materials.

The rendering target was recalibrated offline against distributed cross-volume
samples, including quiet dialogue, intimate two-shots, landscape, action,
monster, crowd, and dramatic full-page material from early, middle, and late
volumes. This provenance explains how the broad rules below were derived; it is
not a runtime selector. Do not automatically retrieve, attach, filter for, or
prefer any fixed volume or page during image generation. Choose a scene-matched
style image dynamically and use it only for mark-making.

Separate authored marks from reproduction artifacts. Ignore JPEG ringing, page skew, uneven paper color, translation font, accidental moire, dust, and scan softness. Reproduce intentional ink, halftone, hatching, composition, and pacing.

## Core manga impression

The target is a scene-conditioned completion band found in clear, economical
late-1990s serialized manga, not one globally sparse finish. Quiet close-ups may
leave broad white areas, while action, monsters, weather, crowds, and establishing
shots may carry substantially more functional information. The stable property
is narrative hierarchy: readable shapes, confident ink decisions, and black-white
rhythm put detail where the story needs it.

For a wide establishing shot, "more functional information" means clearer
silhouette, layout, scale, route, and depth—not more finish on every surface.
Structural completeness and surface completion are different: a shrine can be
credible through its roof mass, major posts, openings, and perspective axes
without describing every tile or wood grain.

- Simplify subordinate information first. Never treat identity-bearing eye
  shape, iris/white balance, bang division, jaw contour, hair silhouette,
  costume layers, or interaction contact as expendable decoration.
- Keep large areas genuinely white or flat black. Use dot tone as a graphic
  layer, not as smooth modeled lighting.
- Concentrate information where the moment needs it. Let redundant folds,
  strands, textures, and background marks fall away, but retain the setting and
  construction cues required to understand the shot.
- Preserve a human-drawn directness: clean and controlled, but not digitally
  perfected, glossy, ornate, or uniformly delicate.
- Even a standalone illustration should feel like a strong manga panel enlarged,
  not key art, a character-painting showcase, or modern prestige line art.

Do not equate manga authenticity with scratchiness or emptiness. The pages are
disciplined and legible; economy means selecting the right marks, not minimizing
their count. A generic anime face inside a sparse coloring-book outline is as
incorrect as glossy prestige line art.

## Visual hierarchy

Build the image from four value groups:

1. White paper and untouched negative space.
2. Clean line art and very light tone.
3. One middle halftone family for garments, mist, or distance.
4. Unbroken black masses for hair, night, silhouettes, effects, and focal accents.

Let white and black carry the image. Use gray as a separator, not as continuous rendered lighting. A successful page remains legible as a small thumbnail.

Set density relative to the selected scene-matched style reference. In a quiet
close-up or intimate two-shot, keep skin clean and backgrounds subordinate while
fully resolving the focal eyes, bangs, jaw, hands, garment overlaps, and contact
chain. In an establishing, action, weather, crowd, or monster shot, allow denser
environment, effects, materials, and motion where they explain place, force, or
scale. Do not translate these observations into arbitrary percentages or maximum
counts for strands, folds, tones, rain lines, or background marks.

In a `wide-shot`, start with a few large white, black, and middle-tone shapes.
Let detail fall away with distance. Untouched paper, broken contours, simplified
materials, and omitted repeated elements are positive authored choices, not
unfinished regions. If the thumbnail reads mainly as uniform fine texture, the
scene is outside the target band even when its perspective is correct.

When correcting an existing `wide-shot`, treat its framing, camera distance,
character scale and placement, major object positions, perspective axes, and
overall black-white distribution as part of the approved scene design. Move the
finish into the target band inside that design. Do not make manga economy more
visible by uniformly emptying the image; do not make manga emphasis more visible
by enlarging the character, recropping the scene, adding large new black areas,
or escalating the drama. Use local contour taper and breaks, clustered marks,
selective density, and distance falloff to refine the drawing without changing
the shot's visual argument.

Reject both sides of the band:

- Over-rendered: strand-by-strand hair, abundant tiny folds, delicate
  micro-texture, smooth volume shading, glossy finish, or uniformly perfected
  digital contours.
- Under-rendered: generic anime faces, identity markers reduced to symbols,
  uniform vector contours, empty architecture, missing garment construction,
  broken hand/object contact, or a coloring-book-like scene with no black-white
  hierarchy.

## Ink and contour

- Simulate a flexible dip pen or G-pen. Start and end strokes with visible taper.
- Draw exterior silhouettes heavier than facial features, fingers, fabric interiors, and distant scenery.
- Allow slight organic wobble. Keep lines confident, not mechanically perfect.
- Break contours selectively at highlights or fast motion.
- Use short parallel hatching for folds, wounds, bark, rock, and deep facial tension.
- Reserve crosshatching for compact shadow pockets. Do not cover the whole image with it.
- Use dry-brush or broken ink only for violent energy, debris, smoke edges, and rough natural materials.

Approximate hierarchy at final resolution:

- Main outer contour: 1.0 unit.
- Secondary clothing/hair contour: 0.65-0.8 unit.
- Facial features and fingers: 0.35-0.5 unit.
- Texture and distant detail: 0.2-0.35 unit.

## Faces and bodies

### Youthful characters

- Use a compact oval or softly squared head with a short chin.
- Place large but simple eyes below the head midpoint; emphasize the upper eyelid.
- Use one or two crisp eye highlights and minimal iris rendering.
- Indicate the nose with a tiny wedge, dot, or short contour; avoid modeled nostrils.
- Keep the mouth small in calm scenes, widening it geometrically for anger, surprise, or comedy.
- Build hair as a readable outer mass first, then add a limited number of tapered locks.
- Preserve the character-specific eye, bang, side-lock, jaw, and hair-silhouette
  relationships even when the surrounding rendering is economical.

### Adults, elders, and villains

- Lengthen the face and sharpen cheek or jaw contours.
- Add age with a few decisive creases, under-eye lines, and hatching rather than realistic skin texture.
- Use heavier black around the eyes or behind the head for menace.

### Anatomy and gesture

- Keep normal adults roughly 6.5-7.5 heads tall, with slim torsos and readable hands.
- Simplify children or comic reactions toward 3-5 heads tall.
- Favor clear gesture and costume silhouette over muscle definition.
- Exaggerate foreshortening in attacks, but keep weapon axis, shoulders, and hips coherent.

## Hair, fabric, costume, and fur

- Render black hair as a solid mass cut by narrow white highlight channels.
- Render light hair mostly white, defining volume with contour and a few internal strands.
- Draw kimono and hakama with broad folds that radiate from shoulders, waist ties, knees, and contact points.
- Use halftone to separate layered garments; avoid airbrushed fabric gradients.
- Let official evidence decide which garment layers, overlaps, motifs, ties, and
  accessories exist; use the selected original only to decide their relative
  paper-white, flat-black, and halftone hierarchy and the strokes that describe
  their fabric and folds.
- Treat patterned cloth as a few bold motifs or tone patches, not tiny all-over ornament unless it is identity-critical.
- Build fur from an outer broken silhouette plus sparse interior tufts. Keep it lighter than adjacent black hair or armor.

## Halftone and texture

- Use two or three dot-screen densities in one image, typically a light 10-20% field and a middle 30-45% field.
- Fade tones with erased white speckle or a clean gradient in dot density, not painterly blur.
- Use stipple clouds behind emotional close-ups and supernatural presences.
- Use dense black-to-dot transitions for night, dread, or poisonous atmosphere.
- Keep skin mostly white. Shade it only with a tiny blush tone, sparse hatching, or a compact cast shadow.
- Avoid fine screens at small output sizes because they collapse into moire.

## Quiet storytelling

- Use four to seven panels for a dialogue-heavy page.
- Alternate horizontal reaction strips, compact two-shots, and one larger emotional anchor panel.
- Simplify or omit backgrounds in close conversation. Reintroduce one establishing panel to maintain place.
- Use generous white around faces and balloons.
- Let a black background, stipple halo, or cropped eye close-up mark an emotional turn.
- Keep expressions readable with eyebrows, eyelids, mouth shape, a sweat drop, or one blush patch; do not over-render.

## Action construction

- Reduce a high-impact page to two to four panels or one dominant splash.
- Establish one main diagonal through body, weapon, attack, or enemy silhouette.
- Aim speed lines toward a clear vanishing point or impact center.
- Crop limbs, clothing, weapons, or effects at the frame edge to increase force.
- Let attacks and sound-effect shapes overlap or break panel borders selectively.
- Construct impact with a white core, black wedges, debris, and radiating line bundles.
- Place one short reaction panel before or after the main hit to control pacing.
- Use blank space around a frozen pose before impact; use dense lines and black after release.

## Monsters and supernatural effects

- Start from a recognizable animal, insect, plant, mask, bone, or human base, then distort one or two dominant traits.
- Favor asymmetry, swollen eyes, layered mouths, segmented limbs, tendrils, scales, or exposed bone.
- Keep the monster silhouette simple enough to read against a busy action field.
- Contrast grotesque textures against clean-faced protagonists.
- Model mass with contour bands, sparse hatching, stipple, and flat black cavities rather than digital 3D lighting.
- Render mist and aura as white negative shapes edged by dots, broken ink, or thin contour.
- Render energy attacks as sweeping white ribbons or blades surrounded by black wedges and speed lines.

## Backgrounds and setting

- Establish one view clearly enough to locate the story: shrine, village,
  forest, field, ruined structure, night sky, or modern street. Describe its
  spatial logic, not every visible surface.
- Simplify repeated backgrounds after location is established.
- In a standalone action image, choose either detailed architecture or detailed foliage, never both alongside a fully rendered creature.
- Draw trees and foliage as clustered black silhouettes plus a few leaf contours.
- Indicate wood, stone, soil, and damage with a few directional strokes on the
  nearest or most informative plane; do not spread material texture uniformly.
- Keep perspective credible through major axes, overlap, scale, and ground
  contact. Reduce distant objects to outline, flat mass, or one restrained tone.
- In a wide establishing shot, preserve roof silhouettes, major posts, openings,
  road or stair direction, and terrain breaks; omit repeated tiles, grain,
  pebble fields, leaf-by-leaf foliage, and all-over rock strata.
- For night, use large black skies with stars, mist, or moon rendered as white interruptions.

## Period modes

### Early-rounded

Use softer chins, rounder eyes, more even panel grids, open white backgrounds, and modest effect lettering. Keep action energetic but less densely layered.

### Classic-balanced

Use compact faces, controlled tones, firm black hair masses, flexible grids, and alternating calm/release pacing. This is the default because it captures the most stable traits across the corpus.

### Late-action

Use sharper eye and hair shapes, larger cropped figures, stronger diagonals, more border-breaking attacks, broader black effect lettering, and higher contrast. Keep faces clean so the page does not become uniformly noisy.

## Color exception

Default to monochrome interior-manga treatment. If the user explicitly requests a cover or color illustration, use a limited flat palette: vermilion, paper white, ink black, muted forest green, dusty blue, ochre, and restrained skin tones. Preserve the ink drawing and avoid glossy digital anime lighting.

## Failure patterns to prevent

- Highly finished black-and-white illustration with strand-by-strand hair,
  abundant tiny folds, delicate micro-texture, or smooth volume rendering.
- Modern prestige line art whose polish and uniform precision overpower the
  direct, page-ready serialized-manga impression.
- Full-color anime art merely desaturated afterward.
- Soft airbrush shading or cinematic bloom.
- Uniform vector outlines with no taper.
- Photorealistic faces, lips, pores, or anatomy.
- Dense gray on every surface, causing low contrast.
- Overly ornate generic fantasy armor.
- Backgrounds with photographic detail in every panel.
- Wide scenes that read as monochrome concept art, engraving, or etching because
  architecture, foliage, rock, and distance all receive the same fine finish.
- Random speed lines without an impact center.
- Excessive gore replacing readable monster design.
- Legible but incorrect AI-generated Chinese or Japanese text.
