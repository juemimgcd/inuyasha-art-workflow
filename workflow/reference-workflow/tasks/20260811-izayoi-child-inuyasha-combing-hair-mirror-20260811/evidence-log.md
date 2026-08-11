# Evidence log

Task: `20260811-izayoi-child-inuyasha-combing-hair-mirror-20260811`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 十六夜成年默认形态的脸型、眼型、长直黑发与贵族和服；幼年犬夜叉 child-form 的幼童比例、犬耳、长白发、童装火鼠裘与赤足结构。
- Source searched: `official` catalog；精确角色形态检索，`medium-shot` 无命中后去掉景别限制。
- Result: `HIT`
- Selected item IDs: `official:file:f4819e9df3546a3ed095`, `official:file:6285125444be8011e070`, `official:file:c72310b3df3a4455f6eb`
- Usable evidence: 十六夜表情设定控制成年面型、较窄眼型与温柔沉静神情；十六夜全身设定控制长发和服层次；幼年犬夜叉四视图控制 child-form 比例、犬耳、长发、童装与赤足。均不控制梳头动作、镜台器物或室内构图。

## Layer 2: Manga or TV screenshots

- Need: 原著黑白漫画中十六夜面部简化、黑发实色块、和服线条及克制网点的画法。
- Source browsed: `manga-curated`，十六夜 `default-form`；`medium-shot` 无命中后查看不限制景别的前三张候选。
- Selected item IDs: `manga-curated:file:876af11c5aa2fd24a707`
- Result: `HIT`
- Controls: 只控制黑白漫画渲染语法，包括蘸水笔轮廓、黑发实色块、面部简化与网点留白关系。
- Must not control: 不复制原图人物姿势、对白、文字、分镜布局、背景或剧情；角色身份由官方设定控制。

## Layer 3: exact content evidence

- Need: 十六夜从幼年犬夜叉身后给他梳头，孩子面向低矮镜台上的圆形抛光铜镜；十六夜一手拢住一束长发，另一手以细齿木梳从上向下梳理，镜面反射孩子脸部与犬耳的空间关系。
- Query: 梳头
- Selected-medium source: manga-curated
- Selected-medium result: `MISS`；按 `medium-shot` 与去掉景别限制两次精确检索均无命中。
- Cross-medium fallback source: tv-curated
- Cross-medium fallback result: `MISS`；按 `medium-shot` 与去掉景别限制两次精确检索均无命中。
- Selected item IDs: N/A
- Exact focus: 十六夜从幼年犬夜叉身后给他梳头，孩子面向低矮镜台上的圆形抛光铜镜；十六夜一手拢住一束长发，另一手以细齿木梳从上向下梳理，镜面反射孩子脸部与犬耳的空间关系。
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP`；用户未要求延续既有已接受输出。
- Selected item IDs: N/A
- Usable evidence: N/A；不使用历史候选或未确认 selected-output 控制本图。

## Historical object provenance

- Result: `HIT` for textual construction facts from Kyoto National Museum; used only to describe period-appropriate utensils, not as rendering or character authority.
- Mirror: Muromachi-period mirrors were bronze/copper-alloy with a polished or tin-coated reflective face; handled mirrors appeared in Japan around the beginning of the 16th century. Use a small round polished bronze mirror in a low portable stand, never a modern glass mirror.
- Combs and boxes: the 1390-period Asuka Shrine toiletry set includes a mirror, combs, hair tools, hand box and a lacquer comb box; use a fine-toothed lacquered wooden comb with a small makie comb box and shallow hand box.
- Sources: https://www.kyohaku.go.jp/eng/learn/home/dictio/kinkou/54dokyo/ ; https://knmdb.kyohaku.go.jp/19215.html ; https://www.kyohaku.go.jp/jp/learn/home/dictio/shikki/199/
