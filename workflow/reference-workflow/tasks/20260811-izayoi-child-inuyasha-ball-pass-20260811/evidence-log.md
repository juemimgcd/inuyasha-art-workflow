# Evidence log

Task: `20260811-izayoi-child-inuyasha-ball-pass-20260811`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 十六夜成年默认形态的长发、贵族和服层次与全身轮廓；幼年犬夜叉的犬耳、长发、幼童体型、童装火鼠裘与赤足结构。
- Source searched: `official` catalog；先按 `shot=action` 检索无命中，再按相同角色和精确形态去掉景别限制检索。
- Result: `HIT`
- Selected item IDs: `official:file:6285125444be8011e070`, `official:file:c72310b3df3a4455f6eb`
- Usable evidence: 十六夜全身正背面和服设定控制身份、发型与衣装；幼年犬夜叉四视图控制 child-form 比例、犬耳、长发、交领宽袖童装和赤足。两张设定图均不控制庭院构图或传球动作。

## Layer 2: Manga or TV screenshots

- Need: 原著黑白漫画中十六夜的线条、黑发实色块、和服网点与人物轮廓处理。
- Source browsed: `manga-curated`，十六夜 `default-form`；按 action 检索无命中后查看不限制景别的前三张候选。
- Selected item IDs: `manga-curated:file:cb67f4934e8e0825eda6`
- Result: `HIT`
- Controls: 只控制黑白漫画渲染语法，包括蘸水笔轮廓、黑发实色块、和服克制网点与留白关系。
- Must not control: 不复制原图人物姿势、对白、文字、分镜布局、背景或剧情；角色身份仍由官方设定控制。

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
- Result: `SKIP`；用户未要求延续既有已接受输出。
- Selected item IDs: N/A
- Usable evidence: N/A；不使用历史候选或未确认的 selected-output 控制本图。
