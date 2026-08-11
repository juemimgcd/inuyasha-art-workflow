# Generation specification

Use case: precise-object-edit
Asset type: black-and-white manga illustration micro-edit
Selected medium: manga
Period mode: classic-balanced

Primary request:
以袖子微调版为唯一整体目标，完全删除正面可见的桔梗左袖。桔梗左臂从犬夜叉头部和上背后方伸向头顶，正面只看见抚发的手；左肩、手臂与宽袖全部被犬夜叉遮挡。原白色袖块区域补回犬夜叉网点火鼠裘与桔梗腰带、袴的自然遮挡关系，其余画面不变。

Identity ledger:
- 犬夜叉 | 青年半妖 | 银白束发、两只头顶犬耳 | 闭眼释然 | 网点火鼠裘、念珠 | 无武器 | 头靠桔梗肩膀 | 不得变成人类或杀生丸
- 桔梗 | 年轻人类巫女 | 齐刘海与披散黑色长发 | 温柔低头 | 白小袖、宽袖、深色长袴、腰带 | 无武器 | 坐姿承托犬夜叉 | 不得变成戈薇或现代服装

Input images:
- Image 1 `manga-curated:file:17fbec650f5e9c032d81` controls mark-making only: tapered ink, black-white massing, clean skin and restrained halftone. Ignore its characters, text, panels, layout and story.
- Image 2 `official:file:149a0334451c6119c480` controls Inuyasha identity only: half-demon face, two top dog ears, light hair, beads and Fire-Rat robe.
- Image 3 `official:file:1f892bd91be108443dad` controls Kikyo identity and shrine-maiden costume only.
- Image 4 `user-supplied:file:e9ccc7ca9026585afa9b` is the sole EDIT TARGET and controls every visible pixel except the incorrect white sleeve block between the two bodies.

Exact localized edit:
Delete the entire white cloth shape between Inuyasha's chest/necklace and Kikyo's torso, including its upper white triangle, curved lower hem, pointed lower flap, internal fold lines and every visible suggestion of Kikyo's raised left sleeve. Do not merely shorten, narrow, fold or reshape it. There must be ZERO visible white sleeve fabric in this front-center region.

Occlusion logic:
Kikyo's raised left shoulder, upper arm, elbow, forearm, sleeve body and cuff all travel behind Inuyasha's head and upper back and are fully occluded from this camera. Only her existing five-fingered left hand remains visible resting on top of Inuyasha's tied hair. The hidden arm path is implied entirely by occlusion; do not draw a connecting sleeve or forearm in front.

Reconstruction of the cleared region:
- Continue Inuyasha's middle-gray halftone Fire-Rat robe naturally through most of the former white sleeve area, matching the existing screen density, weave-free dot pattern, contour direction and robe folds on his chest and shoulder.
- Preserve the existing prayer-bead strand and its contour; the restored robe must sit behind the beads.
- On the right/lower-right edge, reconnect the boundary to Kikyo's existing dark waist tie and dark hakama, preserving their current shape and tone.
- Maintain a simple clean overlap edge where Inuyasha's robe lies in front of Kikyo's waist/torso. Do not fill the area with blank white paper or invent a new garment.

Invariants:
CHANGE ONLY the front-center white sleeve block and the minimal underlying robe/waist area needed to replace it. Keep both faces, eyes, mouths, heads, hair, ribbon, both dog ears, hand and fingers, shoulder contact, beads, collars, torso positions, lap, right-side sleeve, grass, stipple, crop, line quality and halftone unchanged.

Medium:
Classic-balanced monochrome manga print with flexible tapered contours, solid black Kikyo hair, mostly white Inuyasha hair, clean skin and restrained dot screens. Match Image 4 exactly; no restyling.

Avoid:
No visible Kikyo left sleeve in front; no short sleeve flap; no white triangle; no bell shape; no vertical column; no cuff; no visible forearm; no scarf or detached cloth; no extra hand, arm or sleeve; no altered fingers or dog ears; no change to faces, pose, crop, right sleeve or background; no text, speech bubbles, borders, logo, signature or watermark.
