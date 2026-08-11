# Evidence log

Task: `20260811-child-inuyasha-izayoi-ear-play-warm`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 十六夜默认形态与犬夜叉幼年形态的精确身份/年龄覆盖。
- Source searched: `official`（先检索 two-shot，再去除景别限制）
- Result: `INSUFFICIENT`
- Selected item IDs: `official:file:6285125444be8011e070`
- Usable evidence: 十六夜全身、长直发、齐刘海和贵族和服层次为 `HIT`；当前库中的犬夜叉幼年四视图来自未获用户确认的衍生候选，不能作为已确认官方身份依据，因此幼年形态官方覆盖记为 `MISS`，改用一张选定媒介原著幼年形态做受限 form 补证。

## Layer 2: Manga or TV screenshots

- Need: 原著黑白漫画的人物线条、黑白块面、网点节制与温馨双人插图的面部简化。
- Source browsed: `manga-curated`（幼年犬夜叉 two-shot 为 `MISS`，去除景别后找到幼年形态近景；另从十六夜漫画原图中选择完整人物样本）
- Selected item IDs: `manga-curated:file:cb67f4934e8e0825eda6`; form supplement: `manga-curated:file:cd73f043f0439d0ba73d`
- Result: `HIT`
- Controls: 十六夜原著图只控制黑白漫画线条、黑白块面、网点节制和面部简化；幼年犬夜叉原著图只控制孩童比例、幼年脸型、犬耳与头发关系、童装尺度。
- Must not control: 原图对白、气泡、分镜边框、可见姿势、故事情境、角色站位或背景布局。

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
- Usable evidence: N/A；本任务未请求沿用任何已接受成图的连续性。
