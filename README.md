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

## Windows 11 and PowerShell setup

Native Windows is supported. Clone the repository to a short local path such as
`C:\src\inuyasha-art-workflow` (avoid OneDrive-synced folders), open PowerShell
in the clone, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup-windows.ps1
```

The setup script:

- creates `.venv` and installs the runtime and maintenance dependencies there;
- copies the skill to `$HOME\.agents\skills\generate-inuyasha-manga-art`;
- stores `INUYASHA_WORKFLOW_HOME` for the current user;
- enables long paths for this Git checkout;
- rebuilds the machine-local SQLite catalog and validates the workflow.

Restart Codex after setup. The catalog must be rebuilt on Windows because it
contains machine-local filesystem paths. Existing task and attempt JSON remains
unchanged: runtime path aliases map the original macOS prefixes to this clone.

Run an individual workflow command from PowerShell with:

```powershell
$skill = "$HOME\.agents\skills\generate-inuyasha-manga-art"
& "$skill\scripts\run-python.ps1" "$skill\scripts\build_reference_index.py" --check
```

Exit code `0` means the catalog is fresh; exit code `3` means it should be
rebuilt by running the same command without `--check`. `pdftoppm`/Poppler is
optional and needed only when preparing a page directly from a PDF; the bundled
image libraries work without it.

## macOS and Linux checkout

Create the repository-only Python environment once:

```sh
./setup-python-env.sh
```

This installs Pillow and PyYAML only into this checkout's ignored `.venv`. It
does not install packages into system Python, Homebrew Python, the Codex bundled
runtime, another project environment, or a global `PATH` change. Set
`INUYASHA_BOOTSTRAP_PYTHON` for that one command if `python3` is not the desired
bootstrap interpreter.

The checked-in launcher then uses the repository `.venv` and verifies Pillow
before running a workflow command:

```sh
skill/generate-inuyasha-manga-art/scripts/run-python \
  skill/generate-inuyasha-manga-art/scripts/build_reference_index.py --check
```

Configuration is repository-relative on every platform. Set
`INUYASHA_WORKFLOW_HOME` only when the skill is copied outside the clone, and
set `INUYASHA_WORKFLOW_ROOT` only when generated workflow data should live in a
different directory. For a temporary checkout or Git worktree, reuse an existing
project environment for one command without changing global shell state:

```sh
INUYASHA_PYTHON=/absolute/path/to/inuyasha-art-workflow/.venv/bin/python \
  skill/generate-inuyasha-manga-art/scripts/run-python \
  skill/generate-inuyasha-manga-art/scripts/build_reference_index.py --check
```

`requirements.txt` contains runtime dependencies. `requirements-dev.txt`
includes those plus PyYAML for package and skill validation. Launchers never
install packages automatically: a selected but incomplete environment produces
an actionable error instead of silently switching to another Python.

## Privacy and rights notice

This repository is intended as a private backup. Task manifests may retain local filesystem paths and source provenance. Manga panels, TV captures, and official setting sheets remain the property of their respective rights holders and should not be redistributed through a public repository.
