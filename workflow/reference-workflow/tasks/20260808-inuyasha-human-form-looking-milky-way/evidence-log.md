# Evidence log

Task: `20260808-inuyasha-human-form-looking-milky-way`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 犬夜叉人类形态的黑发、普通人耳、脸型、念珠与火鼠裘交领结构
- Source searched: `/Users/jquery/Documents/inuyahsa-official`；先检索 `犬夜叉 + human-form + upper-body`，再仅移除镜头条件回退到 `犬夜叉 + human-form`
- Result: 精确条件 `MISS`；同形态回退 `HIT`
- Selected item IDs: `official:file:efe7eafd42e0ab48e48f`
- Usable evidence: 身份与服装结构。禁止把设定集白发线稿误当做人类形态发色；brief 的黑发规则优先。

## Layer 2: Manga or TV screenshots

- Need: 人类形态的黑白漫画眼型、黑发墨块、皮肤留白和轻网点关系
- Source browsed: `manga-curated`；先检索 `犬夜叉 + human-form + upper-body`，再仅移除镜头条件浏览全部 8 张同形态候选
- Selected item IDs: `manga-curated:file:4979f0e5da216eff0102`
- Result: 精确条件 `MISS`；同形态近景回退 `HIT`
- Controls: 眼睛线条、虹膜比例、黑发留白、漫画墨色与网点密度
- Must not control: 原图正面视角、气泡、分格、背景人物和既有剧情构图

## Layer 3: selected original outputs

- Need: 如有同形态、同镜头且不污染单人黑白构图的既有成片，则用于连续性
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: 精确条件 `MISS`；同形态回退只得到桔梗双人全身的两张彩图和一张花地黑白图，判定 `INSUFFICIENT`
- Selected item IDs: none
- Usable evidence: none；不将双人关系、全身构图或彩色星空带入本次单人漫画上身图
