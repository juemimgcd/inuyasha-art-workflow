# Runtime and package boundary

This checkout is a portable packaging snapshot. It is not the live Codex runtime.

- The live installed skill is
  `/Users/jquery/.codex/skills/generate-inuyasha-manga-art`.
- The live workflow data is
  `/Users/jquery/Documents/inuYasha-design/reference-workflow`.
- This checkout keeps its own portable workflow data under
  `workflow/reference-workflow` and repository-relative library configuration.
- When fixing or tuning the live workflow, change only the installed skill unless
  the user explicitly asks to update this package checkout too.
- Preserve all existing tracked and untracked changes in this checkout. Never use
  a bulk copy, `rsync --delete`, reset, or checkout to make it match the installed
  skill.
- To package selected installed changes, first run
  `python3 tools/sync_installed_skill.py`. Apply only reviewed files with repeated
  `--include` arguments and `--apply`. The tool must stage the proposed files
  against the complete current package, pass package tests and workflow
  validation, create a unique external backup manifest, and only then promote
  the files transactionally. A validation or write failure must leave the
  checkout unchanged.
- Do not bypass the staged gate with direct copies. Use `--allow-dirty` only for
  explicitly reviewed dirty targets; the same validation, backup, and rollback
  requirements still apply.
- Never replace
  `skill/generate-inuyasha-manga-art/references/source-library.json` from the
  installed copy; the two files intentionally point at different data roots.
