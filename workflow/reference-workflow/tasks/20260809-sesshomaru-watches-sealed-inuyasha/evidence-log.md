# Evidence log

Task: `20260809-sesshomaru-watches-sealed-inuyasha`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 杀生丸标准成年妖怪形态的头部标记、侧耳、肩毛、衣甲和佩刀，以及犬夜叉半妖形态的犬耳、言灵念珠、火鼠裘与整体体型
- Source searched: `/Users/jquery/Documents/inuyahsa-official`；先分别检索 `杀生丸 + default-form + two-shot` 与 `犬夜叉 + half-demon-form + two-shot`，再仅移除镜头条件回退
- Result: 杀生丸双人条件只命中与邪见的身高对比图、与本场景不直接相关；犬夜叉双人条件 `MISS`；两个角色同形态回退均为 `HIT`
- Selected item IDs: `official:file:149102d0222789e096e6`, `official:file:798eaba650545b06b4a7`
- Usable evidence: 另人工检查了 `official:file:d81783eb582b92d0a036` 的杀生丸头部表情，但因生成器五图上限不传入；实际传入的全身设定仍覆盖月牙额纹、双颊妖纹、尖侧耳、完整肩毛、纹样衣甲和佩刀轮廓。犬夜叉设定覆盖半妖长发、头顶犬耳、言灵念珠、火鼠裘和赤足结构。只控制身份，不控制画法或构图。

## Layer 2: Manga or TV screenshots

- Need: 安静凝视场景中的黑白漫画侧脸、线条粗细、皮肤留白、浅色头发与克制网点关系
- Source browsed: `manga-curated`；先检索 `杀生丸 + default-form + two-shot`，再仅移除镜头条件浏览全部 5 张同形态候选
- Selected item IDs: `manga-curated:file:1a5ee70d0760b3256408`
- Result: 精确双人条件 `MISS`；同形态侧脸候选 `HIT`
- Controls: 杀生丸侧脸的漫画化简、蘸水笔线条层级、黑白块与浅网点密度
- Must not control: 原图中的文字、具体侧脸姿势、服装裁切、画面布局或既有剧情

## Layer 3: selected original outputs

- Need: 如有同形态、同为黑白静态叙事且适合两兄弟远近构图的既有成片，则用于完成度连续性
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: 精确双人条件仅命中一张日月双背景持刀彩图，与本次安静黑白封印场景的媒介和构图不兼容，判定 `INSUFFICIENT`
- Selected item IDs: none
- Usable evidence: none；不把彩色宇宙背景、并肩持刀姿势或现代数码彩图完成方式带入本次画面
