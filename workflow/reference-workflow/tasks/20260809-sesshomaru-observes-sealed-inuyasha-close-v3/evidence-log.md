# Evidence log

Task: `20260809-sesshomaru-observes-sealed-inuyasha-close-v3`

Run the three retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official setting sheets -> selected-medium screenshots under `origin-photos` -> `/Users/jquery/Documents/inuYasha-design/selected-output`. Do not search later layers in parallel. A `MISS` in selected-output is allowed; never substitute it for missing official identity or selected-medium style evidence.

## Layer 1: official identity

- Need: 杀生丸默认形态近景脸、月牙、脸纹和侧耳；犬夜叉半妖形态全身、犬耳、火鼠裘、念珠与铁碎牙。
- Source searched: `official`; exact `close-up` searches returned `MISS`, then the contract-authorized same-character/same-form fallback without shot returned candidates.
- Result: `HIT`
- Selected item IDs: `official:file:d81783eb582b92d0a036`, `official:file:798eaba650545b06b4a7`
- Usable evidence: 杀生丸头部表情图控制冷静近景脸、额心月牙、双颊妖纹和尖侧耳；犬夜叉半妖形态图控制远景人物的犬耳、长发、念珠、火鼠裘、袴和赤足。封印发生在取得铁碎牙之前，因此犬夜叉身上不出现刀。

## Layer 2: Manga or TV screenshots

- Need: 原作黑白漫画的杀生丸侧脸简化、眼睑、浅色长发、肩毛留白和局部网点。
- Source browsed: `manga-curated`; exact `close-up` returned `MISS`, fallback without shot returned five inspected candidates and a contact sheet.
- Selected item IDs: `manga-curated:file:1a5ee70d0760b3256408`
- Result: `HIT`
- Controls: 侧脸轮廓、眼部简化、浅色长发线束、黑白块和克制网点。
- Must not control: 不复制原图表情、文字、音效、分格、背景或故事内容。

## Layer 3: selected original outputs

- Need: 可选的、同为黑白漫画且能帮助两兄弟连续性的已接受成图。
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `INSUFFICIENT`; exact `close-up` 为 `MISS`，放宽镜头后唯一候选是彩色双人持刀图，与本次黑白封印场景不兼容。
- Selected item IDs: none
- Usable evidence: none; 不让彩色成图覆盖用户本次两张原作漫画参考。
