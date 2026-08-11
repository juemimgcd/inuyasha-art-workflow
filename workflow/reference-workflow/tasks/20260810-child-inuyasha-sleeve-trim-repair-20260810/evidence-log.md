# Evidence log

Task: `20260810-child-inuyasha-sleeve-trim-repair-20260810`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 幼年犬夜叉上臂浅色窄袖带及闭合衣襟结构
- Source searched: `official`
- Result: `MISS`
- Selected item IDs: `N/A`
- Usable evidence: 官方库没有精确幼年设定页；使用用户点名的 TV 幼年截图作为选定媒介 `form` 补证，只控制可见的上臂窄袖带。

## Layer 2: Manga or TV screenshots

- Need: 上臂浅色窄袖带的位置、宽度和环绕方向
- Source browsed: `tv-curated`
- Selected item IDs: `tv-curated:file:647cbeca552efd67d4ad`
- Result: `HIT`
- Controls: 只控制红色外袖肩部下方的浅米色窄袖带；目标图控制全部其余像素与闭合衣襟结构
- Must not control: 不得由截图改动目标图的脸型、比例、动作、场景、配色系统、四视图布局或重新打开红色前襟

## Layer 3: exact content evidence

- Need: N/A
- Query: N/A
- Selected-medium source: tv-curated
- Selected-medium result: SKIP
- Cross-medium fallback source: manga-curated
- Cross-medium fallback result: SKIP
- Selected item IDs: `N/A`
- Exact focus: N/A
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP`
- Selected item IDs: `N/A`
- Usable evidence: 本轮 target 为上一轮未接受但结构正确的任务内候选，不从 selected-output 继承权威。
