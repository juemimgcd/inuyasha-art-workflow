# Evidence log

Task: `20260810-child-inuyasha-turnaround-costume-fix`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 犬夜叉幼年形态的官方身份设定，重点是幼年服装结构
- Source searched: identity-official catalog，query=犬夜叉，subject-form=犬夜叉=child-form
- Result: MISS
- Selected item IDs: N/A
- Usable evidence: 官方身份层无幼年形态命中；本次只修改既有目标图服装，人物身份和外形由目标图锁定，服装以用户指定的TV截图作 form fallback

## Layer 2: Manga or TV screenshots

- Need: 幼年犬夜叉红色上衣、白色领口内衬、胸前系绳与上下装同红色的可见配色关系
- Source browsed: tv-curated
- Selected item IDs: tv-curated:file:402c3966ffc2420a1427
- Result: HIT
- Controls: 红色交领闭合上衣、白色窄领口内衬、胸前小系绳结、上下装同一红色体系、扁平深色腰带与宽红袖
- Must not control: 目标图人物动作、四视图角度、构图、背景、发型、脸部、比例；不复制截图水印

## Layer 3: exact content evidence

- Need: N/A
- Query: N/A
- Selected-medium source: tv-curated
- Selected-medium result: SKIP
- Cross-medium fallback source: manga-curated
- Cross-medium fallback result: SKIP
- Selected item IDs: N/A
- Exact focus: N/A
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP` unless continuity was requested
- Selected item IDs: N/A
- Usable evidence: N/A；目标图作为 edit target 单独置于清单首位，不作为已接受连续性输出
