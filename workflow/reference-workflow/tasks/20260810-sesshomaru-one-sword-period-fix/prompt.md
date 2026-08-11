# Microfix specification

Edit the target image. Change only `construction`: 只删除远景杀生丸腰间多余的一把刀，仅保留一把佩刀，并修顺单刀从腰带到刀鞘的连接、重叠和线条；近景杀生丸、远景人物其他部位、服装、毛皮、长发、姿态、背景、构图、线稿和网点全部保持不变

Input 1 is a context crop, not the full canvas. Modify only the requested area inside source edit box [260, 790, 190, 200]; context came from source box [120, 650, 470, 480]. Keep the crop boundary visually continuous so the edited center can be composited back into the untouched original.


Reference authority:
- Input 1 (target): This is a context crop from the edit target. Change only 只删除远景杀生丸腰间多余的一把刀，仅保留一把佩刀，并修顺腰带到刀鞘的单刀连接；编辑框外完全不变; preserve crop-edge continuity for deterministic compositing into the original.
- Input 2 (identity): Control canonical character identity, form, anatomy, costume, weapon or prop construction, attachment, and scale only. Do not control rendering style or scene composition. This prepared image is a task-local crop (650, 140, 260, 340) from the recorded source; use only construction visible inside the crop and do not infer omitted states. Exact focus: 右侧三分之四站姿的单刀腰间挂载、刀柄护手与刀鞘的前后遮挡；只控制保留的一把刀的连接，不改变目标人物造型

Preserve exactly:
- 父任务中已经通过的角色身份、形态、构图和漫画画法保持不变
- 只处理 construction 类问题，不引入其他设计改动
- 用户对该时期的明确校正优先：腰间总数必须正好一把刀；保留靠人物身体、挂载更自然的那一把，完整移除另一把的刀柄、护手、刀鞘和重复线条
- 生成内容只供声明的编辑框合成，框外像素必须与父图完全一致

Keep the current crop, pose, faces, expressions, character scale, line hierarchy, black-white balance, halftone density, background, and all non-target regions unchanged unless one is the named edit target. Produce one text-free manga image with no speech balloons, panel borders, signature, logo, or watermark. Do not redesign the whole image.
