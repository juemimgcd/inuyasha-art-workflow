# Evidence log

Task: `20260810-izayoi-child-inuyasha-noble-residence-front-facing`

Run the required retrieval layers in order and record one of `HIT`, `MISS`, or `INSUFFICIENT` before advancing: official identity -> selected-medium rendering -> optional exact content -> optional continuity. For exact content, search the selected medium first; open the cross-medium fallback only after a recorded `MISS` or `INSUFFICIENT`. Never substitute cross-medium content for selected-medium style or official identity.

## Layer 1: official identity

- Need: 十六夜成年贵族女性的正面全身身份、发型与分层和服；幼年犬夜叉的精确幼童比例、犬耳、长发、服装尺度与禁用成年道具。
- Source searched: official（按十六夜=default-form、犬夜叉=child-form、full-body 精确检索并逐张检查）
- Result: HIT
- Selected item IDs: official:file:6285125444be8011e070; official:file:4158557fab085f93df87
- Usable evidence: 十六夜全身设定固定极长黑发、柔和刘海、成年贵族女性比例、层叠宽袖宫廷和服与拖地衣摆；幼年犬夜叉本地四视图母版只固定约四到五头身、银白长发、头顶双犬耳、圆润幼年脸、宽大交领衣袖、宽松袴、赤足、无念珠、无铁碎牙。后者不得控制漫画笔触或场景。

## Layer 2: Manga or TV screenshots

- Need: 原著漫画中十六夜场景的柔性墨线、黑发黑块、和服网点与黑白留白关系。
- Source browsed: manga-curated（十六夜=default-form、full-body 精确检索并检查 2 个候选）
- Selected item IDs: manga-curated:file:cb67f4934e8e0825eda6
- Result: HIT
- Controls: 只控制可变粗细蘸水笔线条、黑白块面、黑发高光通道、和服单层网点与背景的简化程度。
- Must not control: 人物身份、幼年形态、台词、对白气泡、原面板布局、原姿势、原故事或新府邸构图。

## Layer 3: exact content evidence

- Need: N/A
- Query: N/A
- Selected-medium source: manga-curated
- Selected-medium result: SKIP
- Cross-medium fallback source: tv-curated
- Cross-medium fallback result: SKIP
- Selected item IDs: N/A
- Exact focus: N/A
- Must not control: identity, form, costume, palette, rendering style, framing, background treatment, or story staging

## Layer 4: selected original outputs

- Need: explicit accepted-output continuity, otherwise `N/A`
- Source searched: `/Users/jquery/Documents/inuYasha-design/selected-output`
- Result: `SKIP` unless continuity was requested
- Selected item IDs: N/A
- Usable evidence: N/A；用户未要求延续既有成图，本任务设计全新构图。

## User-provided composition correction

- Source: `/Users/jquery/Documents/inuyasha-mine/桔梗(右)和十六夜(左).png`
- Result: HIT
- Controls: 只控制十六夜在左朝右、幼年犬夜叉在右朝左、两人相向侧面并互相注视的空间关系。
- Must not control: 桔梗身份、人物服装、成年比例、墓地、火焰、花丛、手持物、黑夜氛围、原图故事或成图风格。
