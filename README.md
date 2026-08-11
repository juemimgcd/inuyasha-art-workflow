# Inuyasha art workflow archive

Private snapshot of the local Codex skill, its reference workflow, source libraries, task history, and selected outputs.

## Repository layout

- `skill/generate-inuyasha-manga-art/` — installed Codex skill, workflow scripts, tests, and reference contracts.
- `workflow/reference-workflow/` — catalog, annotations, contact sheets, task manifests, attempts, prompts, QA records, and generated outputs.
- `libraries/inuyahsa-official/` — official identity and setting-sheet reference library. The original directory spelling is preserved intentionally.
- `libraries/origin-photos/` — curated manga and TV source captures.
- `libraries/inuyasha-mine/` — user-created continuity references.
- `libraries/selected-output/` — user-selected generated outputs.

The snapshot intentionally omits only rebuildable Python bytecode caches and macOS `.DS_Store` files.

## Restore to the original macOS layout

The current workflow records absolute paths. To reproduce the existing installation without editing those records, restore the directories to their original locations:

```zsh
rsync -a skill/generate-inuyasha-manga-art/ ~/.codex/skills/generate-inuyasha-manga-art/
rsync -a workflow/reference-workflow/ ~/Documents/inuYasha-design/reference-workflow/
rsync -a libraries/inuyahsa-official/ ~/Documents/inuyahsa-official/
rsync -a libraries/origin-photos/ ~/Documents/inuYasha-design/origin-photos/
rsync -a libraries/inuyasha-mine/ ~/Documents/inuyasha-mine/
rsync -a libraries/selected-output/ ~/Documents/inuYasha-design/selected-output/
```

After restoring, check the catalog before using it:

```zsh
~/.codex/skills/generate-inuyasha-manga-art/scripts/run-python \
  ~/.codex/skills/generate-inuyasha-manga-art/scripts/build_reference_index.py --check
```

Exit code `0` means the catalog is fresh. Exit code `3` means it should be rebuilt by running the same command without `--check`.

## Privacy and rights notice

This repository is intended as a private backup. Task manifests may retain local filesystem paths and source provenance. Manga panels, TV captures, and official setting sheets remain the property of their respective rights holders and should not be redistributed through a public repository.
