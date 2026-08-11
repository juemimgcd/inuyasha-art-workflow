# Evidence log

Task: `20260808-inuyasha-human-form-wind-sakura`

Default manga tasks use official identity sheets plus one or two inspected screenshots from `origin-photos/manga-photos`. Do not search the complete volumes unless the request needs an exact original scene or a rare detail missing from the setting sheets. Allowed states: `HIT`, `INSUFFICIENT`, `N/A`.

## Identity

- Need: 犬夜叉人类形态的头发、耳朵、脸、火鼠袍、念珠、赤足，以及铁碎牙入鞘后的佩刀位置。
- Source searched: `official`，先检索“犬夜叉 人类形态 全身”，未找到单张同时覆盖全部需求；随后分别检索人类形态与铁碎牙全身设定。
- Result: HIT（人类形态设定图）；审计修正：铁碎牙全身设定图实际是半妖形态，不能作为人类形态生成输入。
- Selected item IDs: `official:file:efe7eafd42e0ab48e48f`, `official:file:b69a31a9412dc8a2a06b`
- Usable evidence: `official:file:efe7eafd42e0ab48e48f` 证明人类形态没有犬耳，长发改为黑色，并保留念珠、火鼠袍与袴、腰带和赤足。`official:file:b69a31a9412dc8a2a06b` 只可供人工检查铁碎牙，不能再传给生成器，因为它会泄漏半妖形态的白发和犬耳。

### 2026-08-08 audit correction

旧工作流把第二张设定图作为 identity 输入是形态兼容性错误。目录索引没有把它标成“人类形态”；错误发生在宽松文本命中后的参考集准备阶段。schema 4 现将它标为 `half-demon-form`，并会阻止它进入声明了 `犬夜叉=human-form` 的任务。

## Manga or TV style references

- Need: 人类形态黑发大色块、安静表情、柔韧墨线、克制网点与风中发丝的漫画画法。
- Source browsed: `manga-curated` 文件夹 `犬夜叉`，并缩小到“犬夜叉 人类形态”8 张截图联系表后逐张检查。
- Selected item IDs: `manga-curated:file:d47d8442e4f7fd7c3875`
- Result: HIT。
- Controls: 黑发的纯黑块与细白高光、轮廓粗细层级、脸部简化、衣服单层网点、背景虚化和留白。
- Must not control: 截图中的人物姿势、相邻人物、对白、面板裁切、原场景和故事；本图构图重新设计。

## Exceptional source lookup

- Reason required: N/A；官方设定和精选截图已经充分。
- Source searched or `N/A`: N/A；没有打开完整漫画卷。
- Result: N/A。
- Selected item IDs or pages: N/A。

## Continuity

- Need: N/A；用户没有要求延续既有作品。
- Source searched: N/A。
- Result: N/A。
- Selected item IDs: N/A。
- Usable evidence: N/A。
