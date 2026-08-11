# Microfix specification

Edit the target image. Change only `medium`: 将整张彩色四视图转换为日本TV动画人物设定资料风格的纯黑白清稿线稿：白底黑线，无平涂、无灰阶、无赛璐璐阴影、无网点；保留完整四视图、人物造型、服装结构、所有比例与位置。


Reference authority:
- Input 1 (target): Preserve this image exactly except for the user's explicitly requested local edit.

Preserve exactly:
- 父任务中已经通过的角色身份、形态、构图、四视图关系和服装结构保持不变
- 只处理 medium 类问题：从彩色TV赛璐璐设定表转为纯黑白动画设定线稿，不引入其他设计改动

Keep the current crop, pose, faces, expressions, character scale, line hierarchy, black-white balance, halftone density, background, and all non-target regions unchanged unless one is the named edit target. Produce one text-free tv image with no speech balloons, panel borders, signature, logo, or watermark. Do not redesign the whole image.
