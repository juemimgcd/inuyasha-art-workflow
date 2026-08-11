# Evidence log

Task: `20260809-sesshomaru-observes-sealed-inuyasha-wide-v3`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 杀生丸默认形态背面全身与佩刀层级；犬夜叉半妖形态全身、犬耳、火鼠裘、念珠与铁碎牙。
- Source searched: `official`; exact `wide-shot` searches returned `MISS`, then the contract-authorized same-character/same-form fallback without shot returned candidates.
- Result: `HIT`
- Selected item IDs: `official:file:feb144894cb1375186a7`, `official:file:798eaba650545b06b4a7`
- Usable evidence: 杀生丸左侧背面视图控制后背轮廓、肩毛、衣摆、后腰佩刀和鞋履；犬夜叉半妖形态图控制犬耳、长发、念珠、火鼠裘、袴和赤足。封印发生在取得铁碎牙之前，因此犬夜叉身上不出现刀；武器状态与封印姿态服从本次请求。

## Layer 2: Manga or TV screenshots

- Need: 原作黑白漫画的杀生丸全身/上身线条层级、肩毛留白、衣纹网点和大块黑白关系。
- Source browsed: `manga-curated`; exact `wide-shot` returned `MISS`, fallback without shot returned five inspected candidates and a contact sheet.
- Selected item IDs: `manga-curated:file:59832195a04d73283979`
- Result: `HIT`
- Controls: 蘸水笔粗细、肩毛边缘、服装黑白分组、克制网点与森林黑块。
- Must not control: 不复制原图人物姿势、文字、音效、分格、树枝布局或故事内容。

Generation note: 用户第一张构图参考已经人工检查并用于编写场景层级，但它在两次输出阶段触发安全系统误判，因此后续生成不再直接传入该位图；封印改用树干上的无文字灵力痕表达。

## Layer 3: selected original outputs

- Need: 可选的、同为黑白漫画且能帮助两兄弟连续性的已接受成图。
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `INSUFFICIENT`; exact `wide-shot` 为 `MISS`，放宽镜头后唯一候选是彩色双人持刀图，与本次黑白封印场景不兼容。
- Selected item IDs: none
- Usable evidence: none; 不让彩色成图覆盖用户本次两张原作漫画参考。
