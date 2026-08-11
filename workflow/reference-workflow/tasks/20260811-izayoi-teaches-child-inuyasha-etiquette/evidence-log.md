# Evidence log

Task: `20260811-izayoi-teaches-child-inuyasha-etiquette`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 十六夜默认形态、和服层次与成年面部比例；犬夜叉幼年形态覆盖。
- Source searched: `official`（先限定 two-shot，再去除景别限制）
- Result: `INSUFFICIENT`
- Selected item IDs: `official:file:6285125444be8011e070`; 幼年形态补证 `manga-curated:file:cd73f043f0439d0ba73d`
- Usable evidence: 十六夜全身、长直黑发、齐刘海、层叠和服与成年比例为 `HIT`。带 two-shot 的十六夜和幼年犬夜叉身份检索均为 `MISS`；当前 official 中的幼年犬夜叉四视图属于未获用户确认的衍生候选，不作为已确认官方身份依据，改用一张原著幼年形态近景对孩童比例、幼年脸、犬耳与头发关系做受限 form 补证。

## Layer 2: Manga or TV screenshots

- Need: 原著黑白漫画的人物线条、黑白块面、克制网点与贵族和服人物简化语法。
- Source browsed: `manga-curated`（幼年犬夜叉 two-shot 为 `MISS`，去除景别后取得幼年 form；另检查十六夜前三张精确候选）
- Selected item IDs: `manga-curated:file:cb67f4934e8e0825eda6`; form supplement `manga-curated:file:cd73f043f0439d0ba73d`
- Result: `HIT`
- Controls: 十六夜原著全身图只控制黑白漫画线条、黑白块面、网点节制、和服层次的漫画化表达；幼年犬夜叉原著近景只控制孩童比例、幼年脸型、犬耳与头发关系以及童装尺度。
- Must not control: 原图对白、气泡、分镜边框、可见姿势、故事情境、人物站位、室内布局或本次母子动作设计。

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
