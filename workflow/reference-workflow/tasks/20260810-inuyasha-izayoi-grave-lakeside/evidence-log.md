# Evidence log

Task: `20260810-inuyasha-izayoi-grave-lakeside`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 成年半妖犬夜叉的头部轮廓、犬耳、长浅色头发、念珠、火鼠裘层次、赤足与成年全身体型
- Source searched: `official`; first with `wide-shot`, then without the shot filter after the exact-shot search returned no matches
- Result: `HIT`
- Selected item IDs: `official:file:798eaba650545b06b4a7`
- Usable evidence: inspected `犬夜叉半妖形态图01.jpg`; front, three-quarter, and back full-body views establish the half-demon form, face, costume layering, silhouette, and adult proportions

## Layer 2: Manga or TV screenshots

- Need: 经典平衡期黑白漫画的安静叙事、可变粗细蘸水笔线条、留白、花草简化和单一中灰网点层级
- Source browsed: `manga-curated`; first with `wide-shot`, then without the shot filter after the exact-shot search returned no matches
- Selected item IDs: `manga-curated:file:b244478bd62b0efcf1f2`
- Result: `HIT`
- Controls: only manga mark-making, clean face treatment, line-weight hierarchy, restrained halftone, negative space, and quiet emotional tone
- Must not control: character identity, the depicted characters, pose, layout, flowers, story, framing, dialogue, or any spatial relationship

## Layer 3: exact content evidence

- Need: 只参考十六夜墓碑的主碑与两侧较小石碑的形制、相对高度，以及墓碑正对湖面的空间关系；不参考TV色彩、线条、光影、构图或角色渲染
- Query: 十六夜墓碑
- Selected-medium source: manga-curated
- Selected-medium result: `MISS`
- Cross-medium fallback source: tv-curated
- Cross-medium fallback result: `MISS`
- Fallback note: the task instead uses the user's locally retained, explicitly content-only tombstone screenshot as a separate composition/scale reference
- Selected item IDs: `N/A` as a curated content role; user-supplied composition/scale reference is recorded separately in the manifest
- Exact focus: 只参考十六夜墓碑的主碑与两侧较小石碑的形制、相对高度，以及墓碑正对湖面的空间关系；不参考TV色彩、线条、光影、构图或角色渲染
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: `N/A`; no accepted-output continuity requested
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP`
- Selected item IDs: `N/A`
- Usable evidence: `N/A`
