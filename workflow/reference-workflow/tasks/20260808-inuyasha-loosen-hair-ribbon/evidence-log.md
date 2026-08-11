# Evidence log

Task: `20260808-inuyasha-loosen-hair-ribbon`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 确认半妖形态犬夜叉的犬耳、浅色长发、额前发束和念珠身份锚点。
- Source searched: `official`，犬夜叉 + `half-demon-form` + `upper-body`。
- Result: `HIT`。
- Selected item IDs: `official:file:149a0334451c6119c480`。
- Usable evidence: 只用于防止局部修图时改变犬夜叉的半妖身份、脸型、犬耳、前发与念珠；目标图中的束发造型由目标图本身控制。

## Layer 2: Manga or TV screenshots

- Need: 保持安静双人场景的原著黑白线条、白皮肤、黑白块面和节制网点。
- Source browsed: `manga-curated`；先查犬夜叉 + 桔梗 + `half-demon-form` + `upper-body` 得到 `MISS`，随后只去掉景别条件。
- Selected item IDs: `manga-curated:file:b244478bd62b0efcf1f2`。
- Result: `HIT`。
- Controls: 仅控制线条层级、黑白平衡、网点节制和安静场景的画法。
- Must not control: 不复制截图中的动作、人物位置、花地、弓、剧情、文字或构图。

## Layer 3: selected original outputs

- Need: 锁定用户已经认可的这张依偎构图、人物比例、完成度和束发连续性。
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `HIT`。
- Selected item IDs: `selected-output:file:b60b6b7356a3d50613de`。
- Usable evidence: 与目标图对应的精选原创版本；只用于保持构图和完成度，不能覆盖目标图的局部编辑要求。
