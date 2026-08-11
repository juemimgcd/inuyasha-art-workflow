# Evidence log

Task: `20260810-adult-inuyasha-grave-left-lake-right-forest-sad-retry`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: N/A，身份、服装与形态保持目标图不变
- Source searched: N/A，edit 使用 target-only
- Result: SKIP
- Selected item IDs: N/A
- Usable evidence: 目标图保持成年半妖犬夜叉与墓碑三石结构

## Layer 2: Manga or TV screenshots

- Need: N/A，黑白漫画线条与网点保持目标图不变
- Source browsed: N/A，edit 使用 target-only
- Selected item IDs: N/A
- Result: SKIP
- Controls: 目标图控制已有漫画画法和人物完成度
- Must not control: N/A

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
- Result: SKIP，连续性由唯一 target 提供
- Selected item IDs: N/A
- Usable evidence: N/A
