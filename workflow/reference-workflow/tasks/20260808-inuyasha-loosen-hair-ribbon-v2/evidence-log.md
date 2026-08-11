# Evidence log

Task: `20260808-inuyasha-loosen-hair-ribbon-v2`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 确认半妖形态犬夜叉的犬耳、浅色长发、额前发束和念珠身份锚点。
- Source searched: `official`，沿用上一轮犬夜叉 + `half-demon-form` + `upper-body` 的串行检索结果。
- Result: `HIT`。
- Selected item IDs: `official:file:149a0334451c6119c480`。
- Usable evidence: 只用于防止局部修图改变犬夜叉的半妖身份、脸型、犬耳、前发与念珠；束发与发绳形态由本轮 target 控制。

## Layer 2: Manga or TV screenshots

- Need: 保持安静双人场景的原著黑白线条、白皮肤、黑白块面和节制网点。
- Source browsed: `manga-curated`；沿用上一轮先查精确景别 `MISS`、随后仅去除景别条件得到的候选。
- Selected item IDs: `manga-curated:file:b244478bd62b0efcf1f2`。
- Result: `HIT`。
- Controls: 仅控制线条层级、黑白平衡、网点节制和安静场景画法。
- Must not control: 不复制截图中的动作、人物位置、花地、弓、剧情、文字或构图。

## Layer 3: selected original outputs

- Need: 锁定用户认可的依偎构图、人物比例、完成度和束发连续性。
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `HIT`。
- Selected item IDs: `selected-output:file:b60b6b7356a3d50613de`。
- Usable evidence: 只用于保持构图、人物关系和完成度，不能覆盖本轮 target 的局部编辑要求。
