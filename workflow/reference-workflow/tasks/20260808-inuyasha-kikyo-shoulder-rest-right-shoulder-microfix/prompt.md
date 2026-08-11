# Generation specification

Use case: precise-object-edit
Asset type: black-and-white manga anatomy micro-edit
Selected medium: manga
Period mode: classic-balanced

Primary request:
以袖子完全隐藏版为唯一整体目标，只微调犬夜叉画面右侧、靠桔梗一侧的肩膀外轮廓。将过宽、过圆、向右下鼓出的肩部适度向内和向上收窄，使其与另一侧肩宽及斜靠姿势协调；保持桔梗左袖完全隐藏，其他画面全部不变。

Input images:
- Image 1 controls manga mark-making only; do not copy characters, text, layout or story.
- Image 2 controls Inuyasha half-demon identity and canonical upper-body proportions only.
- Image 3 controls Kikyo identity and shrine-maiden costume only.
- Image 4 is the sole EDIT TARGET and controls every visible pixel except Inuyasha's screen-right shoulder contour and the minimal adjacent fill.

Exact localized edit:
In Image 4, identify Inuyasha's shoulder on the viewer's RIGHT, the shoulder closest to Kikyo. Its current outer contour bulges too far right and down, making this side substantially wider and rounder than his opposite shoulder. Pull this shoulder contour inward toward Inuyasha's torso and slightly upward. Reduce the visible width and volume by roughly 10-15 percent, using a gentle descending slope from the base of his neck to a modest shoulder peak and then toward the upper arm/chest. Keep the adjustment subtle, not narrow or bony.

Garment reconstruction:
Redraw only the affected Fire-Rat robe contour and a few broad fold lines so the middle-gray halftone remains continuous and matches the neighboring robe exactly. The robe should drape loosely over a believable shoulder, without a spherical bulge. Preserve the necklace strand in front of the robe. Where the shoulder is pulled inward, reveal only the logically underlying portion of Kikyo's existing white torso/overlap edge and dark waist area. Do not create or reveal Kikyo's hidden left sleeve.

Hard invariants:
- CHANGE ONLY Inuyasha's screen-right shoulder outline, the immediately adjacent robe halftone/folds, and the tiny newly revealed overlap area.
- Keep Inuyasha's head, face, closed eyes, ears, hair, ribbon, neck, necklace, left shoulder, torso angle and lap unchanged.
- Keep Kikyo's face, gaze, hair, hand and five fingers, torso, collar, obi, hakama and visible right sleeve unchanged.
- Kikyo's raised left arm and left sleeve remain completely behind Inuyasha; there must be zero white sleeve fabric in front-center.
- Keep shoulder contact, crop, grass, stipple, linework, halftone density and black-white balance unchanged.

Required visible result:
Inuyasha's two shoulders read as belonging to one slim torso in a relaxed diagonal lean. The screen-right shoulder is slightly foreshortened by contact with Kikyo and no longer appears much wider, lower or rounder than the screen-left shoulder.

Avoid:
No moving the head or neck; no changing the face, ears, hair, hand, beads or pose; no narrow pinched shoulder; no muscular or armored shoulder; no new white sleeve, arm or cloth in front; no changed Kikyo costume; no restyling; no text, speech bubbles, borders, logo, signature or watermark.
