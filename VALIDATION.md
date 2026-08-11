# Snapshot validation

Validation performed before the initial private GitHub upload on 2026-08-11.

## Passed checks

- Checksum-based `rsync` dry runs reported no differences between the six source roots and this repository snapshot, excluding only `__pycache__`, Python bytecode, and `.DS_Store`.
- Codex skill quick validation: `Skill is valid!`
- Unit tests: 57 passed.
- Reference catalog freshness: fresh.
- Workflow validation: `ok: true`, with 248 unique catalog images and 277 image locations.
- Reference feedback report completed successfully over 79 recorded attempts.

## Historical task audit

`validate_all_tasks.py` inspected final/accepted task records:

- 11 tasks passed final validation.
- 2 legacy tasks were already archived because their historical evidence could not be repaired without rewriting what had actually been used.
- 1 task failed final validation: `20260810-kagome-to-sesshomaru-panel-edit`. Its QA checklist is incomplete even though the task is marked final.

The failing and archived historical records are preserved unchanged. This repository is a faithful backup, not a migration that rewrites prior evidence.

## Windows PowerShell adaptation

Validation performed on 2026-08-11 for branch `agent/windows-powershell`:

- Codex skill quick validation: `Skill is valid!`
- Unit tests: 62 passed, including repository-token expansion and legacy path
  mapping with Windows separators.
- A clean temporary workflow root rebuilt successfully from all bundled source
  libraries: 248 unique images, 277 image locations, and 282 legacy aliases.
- The rebuilt catalog passed `--check` and `validate_workflow.py` with `ok: true`.
- The historical task audit against the rebuilt portable catalog kept the same
  baseline: 11 passed, 2 archived, and the one incomplete-QA task listed above
  failed. No historical task, attempt, or acceptance record was rewritten.
- GitHub Actions exercises Python 3.12 on Windows, macOS, and Ubuntu and invokes
  the native PowerShell launcher on `windows-latest`.
