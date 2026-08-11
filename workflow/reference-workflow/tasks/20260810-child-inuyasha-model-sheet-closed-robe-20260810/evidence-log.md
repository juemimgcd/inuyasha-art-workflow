# Evidence log

Task: `20260810-child-inuyasha-model-sheet-closed-robe-20260810`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 幼年犬夜叉胸前衣襟与系绳的精确服装结构
- Source searched: `official`
- Result: `MISS`
- Selected item IDs: `N/A`
- Usable evidence: 官方库没有幼年犬夜叉精确设定页；使用用户点名的 TV 幼年截图作为选定媒介 `form` 补证，仅控制可见的闭合交领、胸前细绳结与黑色内领露出范围。

## Layer 2: Manga or TV screenshots

- Need: 目标图已经建立的 TV 制作设定画法
- Source browsed: 目标图本身
- Selected item IDs: `N/A`
- Result: `SKIP`
- Controls: 目标图控制全部既有轮廓、配色、阴影、布局和未修改区域
- Must not control: TV 截图不得覆盖目标图的脸型、比例、视角或布局，只能补证衣襟闭合结构

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
- Result: `SKIP` unless continuity was requested
- Selected item IDs: `N/A`
- Usable evidence: `SKIP`，本次是对用户刚否决候选的服装结构修正，不调用 selected-output。

## Iteration note: sleeve-trim repair

- Target: 第一次修订得到的闭合交领候选；控制全部未修改像素、人物结构、四视图布局与新衣襟结构。
- Form evidence: `tv-curated:file:647cbeca552efd67d4ad`；本轮只补证上臂浅色窄袖带的位置、宽度和环绕方向。
- Forbidden inference: 不得由截图改动脸型、比例、动作、场景、配色系统或重新打开红色前襟。
