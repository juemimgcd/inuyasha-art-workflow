# Edit specification

Requested edit: 只把十六夜当前指向犬夜叉衣领、扶着他肩膀的双臂改成明确的亲身示范动作：十六夜在自己胸腹前自然地将双手分别藏入对侧宽袖，形成端正、克制、容易模仿的袖手姿势，让画面一眼读出她正在示范给犬夜叉看。十六夜的脸、发型、躯干、和服纹样保持不变；犬夜叉的脸、犬耳、头发、藏袖姿势和全身完全保持不变；框外像素不变。
Selected medium: manga

Input 1 is a context crop, not the full canvas. Modify only the requested area inside source edit box [120, 400, 840, 620]; context came from source box [24, 304, 1032, 812]. Keep the crop boundary visually continuous so the edited center can be composited back into the untouched original.


Identity requirements:
- 犬夜叉 (child-form): 长发；幼童体型与明显孩童头身比；银白长发；头顶双犬耳；圆润幼年脸型；幼童尺寸的火鼠裘交领宽袖与宽松袴；火鼠裘在彩色设定中为红色，在黑白漫画中必须表现为明显深于白发、皮肤与内襟的深色块或网点；深色腰带；赤足；无言灵念珠；无铁碎牙；不得混入杀生丸的额头月牙、脸纹、肩部毛皮或侧耳
- 十六夜 (default-form): required form `default-form`

Reference authority:
- Input 1 (target): This is a context crop from the edit target. Change only 只把十六夜当前指向犬夜叉衣领、扶着他肩膀的双臂改成明确的亲身示范动作：十六夜在自己胸腹前自然地将双手分别藏入对侧宽袖，形成端正、克制、容易模仿的袖手姿势，让画面一眼读出她正在示范给犬夜叉看。十六夜的脸、发型、躯干、和服纹样保持不变；犬夜叉的脸、犬耳、头发、藏袖姿势和全身完全保持不变；框外像素不变。; preserve crop-edge continuity for deterministic compositing into the original.

Preserve:
- 来源候选图中未被点名的角色身份、形态、构图和漫画画法保持不变
- 只处理 composition 类问题，不引入其他设计改动
- 生成内容只供声明的编辑框合成，框外像素必须与来源图完全一致

Use the target as the exact continuity and composition authority. Change only what the request requires. Keep official references limited to identity, selected-medium style screenshots limited to rendering, and content references limited to their exact focus. No unrequested text, balloons, borders, signature, logo, or watermark.
