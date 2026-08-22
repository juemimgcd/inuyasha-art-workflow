# Official character identity guide

Use this guide for identity, costume, equipment, transformations, and relative scale. Use the manga corpus separately for black-and-white rendering style.

## Authority and inspection protocol

The setting-sheet root is `/Users/jquery/Documents/inuyahsa-official` (keep the directory's existing spelling). This directory contains the 设定集. Treat each `<角色>设定集` folder as authoritative for that named character's canonical structural identity. Use `source-map.md` to distinguish it from the user's original art, selected outputs, manga screenshots, and TV screenshots. When the user explicitly requests one of their original variants from `/Users/jquery/Documents/inuyasha-mine`, preserve that variant instead of silently replacing it with the canonical form.

For every named character:

1. Resolve the prompt name to exactly one canonical Chinese name in the index below.
2. List that character's official files before selecting references:

   ```bash
   find "/Users/jquery/Documents/inuyahsa-official/<角色>设定集" -maxdepth 1 -type f -iname '*.jpg' -print | sort
   ```

3. Inspect one face/expression sheet and one full-body/costume sheet when both exist. Also inspect a weapon, action, form, scar, or scale sheet when the requested scene depends on it. If a required back view or attachment detail is small inside a multi-view sheet, pass a focused task-local crop with recorded coordinates rather than extra whole sheets. Only pass sheets whose indexed form matches the requested character form.
4. Write a compact identity ledger before the image prompt: `角色｜年龄/形态｜头发与头部轮廓｜面部标记｜服装｜武器/道具｜体型关系`.
5. Translate the ledger into observable prompt details. Keep canonical markers even when pose, camera, or manga period changes.
6. After generation, compare the output with the same setting sheets. Reject name swaps and borrowed features before judging the drawing style.

For group scenes, inspect `/Users/jquery/Documents/inuyahsa-official/珊瑚-弥勒-犬夜叉-杀生丸-戈薇-桔梗-七宝-云母-枫婆婆全身身高对比图01.jpg` and preserve the depicted height relationships. This sheet includes only part of the cast; do not extrapolate absent characters from it.

## Canonical index

Latin aliases below are only name resolution aids. The inspected setting sheets, not the alias, define the appearance.

| Canonical name | Common prompt aliases | Official identity anchors and required branches |
| --- | --- | --- |
| 犬夜叉 | Inuyasha | Choose explicitly among child, half-demon, human, and without-fire-rat-robe sheets. Child form has long light hair, top dog ears, clear four-to-five-head child proportions, and a child-sized fire-rat robe: red in color evidence and visibly dark against white hair, skin, and inner collar in monochrome output; it has no Beads of Subjugation or Tessaiga. Half-demon form has long light hair and top dog ears; human form has dark hair and no dog ears. The fire-rat robe, beads, bare feet, and Tessaiga remain separate observable details. The local “犬夜叉全身图带铁碎牙01.jpg” sheet is half-demon-form and must not be passed to a human-form or child-form task, even for weapon scale. |
| 戈薇 | Kagome, Kagome Higurashi | Modern teenage schoolgirl with long dark hair and a sailor-style school uniform; bow, quiver, backpack, winter uniform, and casual outfit have separate sheets. Do not put her in Kikyo's priestess costume unless the user explicitly requests a costume change. |
| 桔梗 | Kikyo, Kikyou | Young shrine maiden with straight dark hair, blunt bangs and long side sections, white kosode, long hakama, and bow. Her restrained face and period priestess silhouette must remain distinct from Kagome's schoolgirl silhouette. |
| 杀生丸 | Sesshomaru | Tall adult demon with very long light hair, pointed ears, forehead crescent, cheek markings, large shoulder fur, layered patterned robes/armor, claws, and swords. Inspect the head sheet, a full-body sheet, upper-costume details, and sword sheet as required. Do not give him Inuyasha's dog ears, fire-rat robe, beads, or Tessaiga. |
| 弥勒 | Miroku | Young monk with short dark hair, layered monk robes, sandals, ringed staff, and prayer beads sealing the Wind Tunnel on one hand. Inspect the staff, bead detail, and Wind Tunnel action sheets when used. |
| 珊瑚 | Sango | Choose exactly one of two forms. Demon-slayer form has loose long hair, a long cross-collar work robe, tied waist, shaded wrist guards, leggings, and sandals. Battle-armor form has a high ponytail, fitted patterned armor, shoulder guards, forearm and knee protection, boots, and the giant Hiraikotsu silhouette. Never mix the two hairstyles or clothing systems, and never replace Hiraikotsu with Kagome or Kikyo's bow. |
| 七宝 | Shippo, Shippou | Very small fox-demon child with a high tied hair tuft, fox ears/traits, and a large fox tail. Preserve child scale. Fox-fire effect has its own sheet. Do not turn him into Kirara or a generic human child. |
| 云母 | Kirara | Cat demon with pointed dark ears, a forehead diamond mark, large oval eyes, and two striped tails. Choose explicitly between tiny companion form and giant fanged combat/flying form; both forms retain the two-tail identity. |
| 邪见 | Jaken | Very short imp-like retainer with huge round eyes, pointed ears, beak-like mouth, small robed body, and staff. Use the Sesshomaru height-comparison sheet when they appear together. |
| 玲 | Rin | Human girl with child proportions, shoulder-length dark hair with uneven bangs and a small tied tuft near the crown/back, and a simple patterned kimono. Keep her distinct from young Kaede and Shippo; inspect her full-body/expression sheet rather than inferring from age alone. |
| 琥珀 | Kohaku | Young male demon slayer with tied-back hair and youthful facial construction. The local official folder currently contains a head/expression sheet only; do not claim that it verifies a full costume or weapon. For a full-body combat depiction, inspect a directly relevant manga page or a user-provided reference. |
| 钢牙 | Koga, Kouga | Athletic young wolf-demon with a high ponytail, headband, pointed ears, fur-trimmed tribal armor, exposed limbs, and clawed fighting gestures. Inspect full equipment and face sheets. |
| 神乐 | Kagura | Adult woman with hair gathered into a high bun, dangling earrings, bare feet, bold striped/pinwheel-pattern kimono, and a folding fan. A back-scar sheet exists. Do not give her Kanna's child body, white bob, plain kimono, or mirror. |
| 神无 | Kanna | Small pale child with straight light bobbed hair, blunt bangs, side flower ornaments, plain long kimono, and a round mirror held at the torso. Keep her expression subdued. Do not give her Kagura's adult proportions, bun, patterned kimono, fan, or back scar. |
| 十六夜 | Izayoi | Adult human noblewoman with very long dark hair, soft bangs, and layered courtly kimono. Use her full-body and expression sheets; do not substitute Kikyo's priestess clothing. |
| 枫婆婆 | Kaede, elderly Kaede | Elderly shrine woman with a single eye patch, headscarf, short stooped body, priestess clothing, and bow. Treat her as a separate age state from 幼年枫. |
| 幼年枫 | young Kaede, child Kaede | Human girl with child proportions, tied-back short hair, period clothing, and the younger face shown in the full-body/expression sheet. Do not age her into 枫婆婆 or borrow Rin's hair and kimono. |
| 刀刀斋 | Totosai, Toutousai | Tiny elderly swordsmith with bald crown, wispy hair, prominent eyes and nose, beard, small robed body, and comic proportions. A separate sheet shows him riding 哞哞. |
| 哞哞 | Totosai's ox | Three-eyed horned ox-like flying mount shown with cloud/flame motion. It is not Kirara and must not inherit cat ears, forehead diamond, fangs, or two striped tails. |
| 戈薇爷爷 | Grandpa Higurashi | Elderly modern-shrine family member with swept-back tied hair, long split mustache and pointed beard, and robed silhouette. Inspect either full-body/expression sheet rather than using a generic village elder. |
| 普通人物 | villagers, travelers, samurai, foot soldiers | Non-canonical background people. Select the exact sheet for villager, traveler, young man, samurai armor, foot archer, mounted traveler, or group. Never relabel one as a named cast member. |

## High-risk confusion checks

### 戈薇 versus 桔梗

- 戈薇: modern school uniform or explicitly selected modern casual/winter outfit; long loose hair; modern backpack and school shoes may appear.
- 桔梗: period shrine-maiden layers, long hakama, straight formal hair treatment, and bow.
- Shared facial resemblance is not permission to exchange costumes, age presentation, or era markers.

### 神乐 versus 神无

- 神乐: adult, high bun, earrings, patterned kimono, folding fan, optional back scar.
- 神无: child, straight light bob, flower ornaments, plain kimono, round mirror.
- Never blend the fan and mirror into one character.

### 犬夜叉 versus 杀生丸

- 犬夜叉: top dog ears, bead necklace, loose fire-rat outfit, barefoot, Tessaiga.
- 杀生丸: no top dog ears; pointed side ears, forehead crescent, cheek markings, shoulder fur, armor/patterned robes, multiple swords.

### Small companions

- 七宝 is a small humanoid fox child with one prominent fox tail.
- 云母 is a four-legged cat demon with a forehead mark and two tails, in tiny or giant form.
- 哞哞 is a three-eyed horned ox mount.
- 邪见 is a tiny robed humanoid retainer; 玲 and 幼年枫 are human girls.

## Reference-passing order

Pass the smallest adequate set and follow `reference-manifest.json` exactly:

1. Put the user target first for an edit or exact continuation.
2. Use the bundled medium guide as the default rendering baseline. For a new
   image, add a dynamically selected rendering reference when the scene needs it.
   For a general manga-medium edit, keep the target first and do not add a style
   image unless a scene-specific ink, tone, effect, or period treatment remains
   unresolved. Never select by a fixed volume or page.
3. Add one official sheet that best covers the focal character's required face, form, and costume.
4. Add a second official face, full-body, weapon, action, or scale sheet only for a named unresolved identity need and only when its character form is compatible with the task.
5. Add a separate composition reference only when the selected rendering reference cannot resolve the requested camera or pose.
6. Add at most one exact-focus `content` reference only when the requested action,
   object, creature, effect phase, or spatial fact is unresolved. Search the
   selected medium first; use the other medium only after a recorded miss or
   insufficiency. A cross-medium content image never controls named-character
   identity, costume, form, or rendering.

For a multi-character request, add the minimum official evidence needed to bind each focal character, even if the set exceeds the normal two-to-four-image target. Do not replace identity sheets with unrelated manga panels and do not pass every available setting sheet; excess references weaken feature binding.

If the only evidence for an entity or form is genuinely anime-original, identify
it as a TV-derived design translated into the requested medium. Do not promote a
TV frame to manga-canonical identity authority. Shared named characters still
require their compatible official identity sheets.
