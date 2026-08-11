# Evidence log

Task: `20260811-izayoi-demonstrates-sleeve-hidden-posture`
Parent task: `20260811-izayoi-teaches-child-inuyasha-etiquette`
Intent: `edit`

## Inherited evidence

- Parent task: `20260811-izayoi-teaches-child-inuyasha-etiquette`
- Parent medium: `manga`
- Identity forms: `{'犬夜叉': 'child-form', '十六夜': 'default-form'}`
- Result: `HIT`; inherit the parent's inspected evidence and recorded candidate output.

## Change-specific evidence

- Category: `composition`
- Requested change: 只把十六夜当前指向犬夜叉衣领、扶着他肩膀的双臂改成明确的亲身示范动作：十六夜在自己胸腹前自然地将双手分别藏入对侧宽袖，形成端正、克制、容易模仿的袖手姿势，让画面一眼读出她正在示范给犬夜叉看。十六夜的脸、发型、躯干、和服纹样保持不变；犬夜叉的脸、犬耳、头发、藏袖姿势和全身完全保持不变；框外像素不变。
- Prepared evidence: `target context crop`
- Result: `HIT`; target controls all unchanged regions. Added references control only their manifest roles.

- Local edit mode: `crop-composite`
- Source edit box: `[120, 400, 840, 620]`
- Prepared context box: `[24, 304, 1032, 812]`
- After generation: run `composite_local_microfix.py` before QA and attempt recording.

