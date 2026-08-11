# Evidence log

Task: `20260810-adult-inuyasha-facing-izayoi-grave-lake`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 成年半妖犬夜叉的全身比例、犬耳、长发、火鼠裘、袴、赤足、念珠、铁碎牙佩挂关系
- Source searched: official，先按 犬夜叉=half-demon-form + full-body 精确检索
- Result: HIT
- Selected item IDs: official:file:b69a31a9412dc8a2a06b
- Usable evidence: 全身轮廓、服装层次、赤足接地和铁碎牙腰侧佩挂；不控制漫画网点、湖岸场景或构图

## Layer 2: Manga or TV screenshots

- Need: 安静纪念场景所需的原著漫画黑白线条、浅网点、白色负空间与成年半妖犬夜叉侧面画法
- Source browsed: manga-curated；full-body 精确筛选无候选，记录 INSUFFICIENT 后仅移除 shot，检查前四个候选
- Selected item IDs: manga-curated:file:b244478bd62b0efcf1f2
- Result: HIT
- Controls: 仅控制柔韧线条、白皮肤、浅网点、黑白层级和安静场景的留白节奏
- Must not control: 不复制参考截图中的桔梗、花地、坐姿、人物位置、表情剧情或任何具体构图

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
- Result: SKIP，用户未要求延续任何已接受成图
- Selected item IDs: N/A
- Usable evidence: N/A
