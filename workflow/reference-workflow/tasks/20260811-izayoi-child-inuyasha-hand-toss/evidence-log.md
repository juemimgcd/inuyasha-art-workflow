# Evidence log

Task: `20260811-izayoi-child-inuyasha-hand-toss`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 延续上一张候选图中的十六夜与幼年犬夜叉身份、年龄、服装和相对比例。
- Source searched: 用户在本轮明确指定的上一张候选图。
- Result: HIT
- Selected item IDs: `user-supplied:file:52f4f3793582c3add9abed7`
- Usable evidence: 目标图控制两名角色的现有身份、服装、比例、庭院环境和漫画媒介；本轮请求只重构手上传球动作。

## Layer 2: Manga or TV screenshots

- Need: 延续目标图的黑白漫画线条、网点和建筑处理。
- Source browsed: 用户指定目标图。
- Selected item IDs: `user-supplied:file:52f4f3793582c3add9abed7`
- Result: HIT
- Controls: 目标图控制漫画画法、庭院风格、人物服装和整体视觉语言。
- Must not control: 原图的踢球动作；本轮必须改为十六夜手持球、犬夜叉双手举起等球。

## Layer 3: exact content evidence

- Need: N/A；指定目标图已解决球的形制与尺度，本轮请求直接解决新动作。
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
- Usable evidence: N/A；当前图是用户明确指定的编辑目标，不作为已接受 selected-output 连续性使用。
