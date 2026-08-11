# Evidence log

Task: `20260810-izayoi-grave-lineart-setting-sheet`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 无角色身份；本任务仅生成墓碑道具设定
- Source searched: N/A
- Result: SKIP
- Selected item IDs:
- Usable evidence:

## Layer 2: Manga or TV screenshots

- Need: TV动画中的墓碑可见结构与比例
- Source browsed: 用户提供的两张TV动画截图
- Selected item IDs: user-supplied:file:d1f6b39c1717d915ec76; user-supplied:file:2d1c041cac7dd654044e
- Result: HIT
- Controls: 主碑正面、背面厚度、圆顶轮廓、磨损刻痕与三块石构件的相对位置
- Must not control: 截图字幕、花草、昆虫、湖景、森林、配色、光影和视频画面裁切

## Layer 3: exact content evidence

- Need: 只参考十六夜墓碑群的主碑轮廓、厚度、磨损刻痕与三块石碑的相对位置
- Query: 十六夜墓碑
- Selected-medium source: tv-curated
- Selected-medium result: HIT（用户提供的两张TV动画原始截图）
- Cross-medium fallback source: manga-curated
- Cross-medium fallback result: 
- Selected item IDs: user-supplied:file:d1f6b39c1717d915ec76; user-supplied:file:2d1c041cac7dd654044e
- Exact focus: 只参考十六夜墓碑群的主碑轮廓、厚度、磨损刻痕与三块石碑的相对位置
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: SKIP（未请求连续性）
- Selected item IDs:
- Usable evidence:
