#!/usr/bin/env python3
"""Preview or safely package selected files from the installed live skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SOURCE = Path.home() / ".codex/skills/generate-inuyasha-manga-art"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = REPOSITORY_ROOT / "skill/generate-inuyasha-manga-art"
PROTECTED_PATHS = frozenset({Path("references/source-library.json")})
PROTECTED_PATH_KEYS = frozenset(
    path.as_posix().casefold() for path in PROTECTED_PATHS
)
IGNORED_NAMES = frozenset({".DS_Store"})
IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})


class StagedValidationError(RuntimeError):
    """Raised when a proposed package update fails before repository mutation."""


@dataclass(frozen=True)
class FileStatus:
    path: str
    state: str
    dirty: bool
    protected: bool
    source_sha256: str
    destination_sha256: str | None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"include path must stay inside the skill: {value}")
    return relative


def is_protected(relative: Path) -> bool:
    """Protect named package files on case-insensitive filesystems too."""
    return relative.as_posix().casefold() in PROTECTED_PATH_KEYS


def safe_join(root: Path, relative: Path, label: str) -> Path:
    """Return a path below root while rejecting every symlinked path component."""
    root = root.resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} path contains a symlink: {relative}")
    resolved_parent = current.parent.resolve(strict=False)
    if not resolved_parent.is_relative_to(root):
        raise ValueError(f"{label} path escapes its root: {relative}")
    if current.exists() and not current.resolve().is_relative_to(root):
        raise ValueError(f"{label} path escapes its root: {relative}")
    return current


def source_files(root: Path) -> list[Path]:
    files = []
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        safe_join(root, relative, "installed source")
        if "__pycache__" in relative.parts:
            continue
        if candidate.name in IGNORED_NAMES or candidate.suffix in IGNORED_SUFFIXES:
            continue
        files.append(relative)
    return sorted(files, key=lambda item: item.as_posix())


def reject_tree_symlinks(root: Path, label: str) -> None:
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            relative = candidate.relative_to(root)
            raise ValueError(f"{label} contains a symlink: {relative}")


def selected_files(root: Path, includes: list[str]) -> list[Path]:
    if not includes:
        return source_files(root)
    selected = []
    for raw in includes:
        relative = safe_relative(raw)
        source = safe_join(root, relative, "installed source")
        if not source.is_file():
            raise ValueError(f"installed source file does not exist: {relative}")
        selected.append(relative)
    return sorted(set(selected), key=lambda item: item.as_posix())


def repository_for(destination_root: Path) -> Path:
    process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=destination_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise ValueError("destination is not inside a Git checkout")
    return Path(process.stdout.strip()).resolve()


def git_dirty(repository: Path, destination_root: Path, relative: Path) -> bool:
    destination = safe_join(destination_root, relative, "package destination")
    try:
        repository_relative = destination.relative_to(repository)
    except ValueError as exc:
        raise ValueError("destination must stay inside the package repository") from exc
    process = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            repository_relative.as_posix(),
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "git status failed")
    if process.stdout.strip():
        return True
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", repository_relative.as_posix()],
        cwd=repository,
        check=False,
    )
    if ignored.returncode not in {0, 1}:
        raise RuntimeError("git check-ignore failed")
    return ignored.returncode == 0


def inspect_file(
    repository: Path, source_root: Path, destination_root: Path, relative: Path
) -> FileStatus:
    source = safe_join(source_root, relative, "installed source")
    destination = safe_join(destination_root, relative, "package destination")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"package destination is not a regular file: {relative}")
    source_hash = sha256(source)
    destination_hash = sha256(destination) if destination.is_file() else None
    state = (
        "identical"
        if destination_hash == source_hash
        else "different"
        if destination_hash is not None
        else "missing"
    )
    return FileStatus(
        path=relative.as_posix(),
        state=state,
        dirty=git_dirty(repository, destination_root, relative),
        protected=is_protected(relative),
        source_sha256=source_hash,
        destination_sha256=destination_hash,
    )


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def run_validation_command(
    name: str, command: list[str], repository: Path, environment: dict[str, str]
) -> str:
    process = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(
        part.strip() for part in (process.stdout, process.stderr) if part.strip()
    )
    if process.returncode != 0:
        detail = output[-6000:] if output else f"exit code {process.returncode}"
        raise StagedValidationError(f"staged validation failed ({name}):\n{detail}")
    return name


def validation_python(repository: Path) -> Path:
    candidates = []
    virtualenv_entries = (
        (Path(".venv/Scripts/python.exe"), Path(".venv/bin/python"))
        if os.name == "nt"
        else (Path(".venv/bin/python"), Path(".venv/Scripts/python.exe"))
    )
    for root in (repository, REPOSITORY_ROOT):
        candidates.extend(root / entry for entry in virtualenv_entries)
    candidates.append(Path(sys.executable))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            process = subprocess.run(
                [str(candidate), "-c", "import PIL"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if process.returncode == 0:
            return candidate.absolute()
    raise StagedValidationError(
        "no validation Python with Pillow was found in the package or tool venv"
    )


def normalize_staged_config_for_catalog(
    staged_skill: Path, workflow: Path
) -> None:
    config_path = staged_skill / "references/source-library.json"
    if not config_path.is_file():
        return
    catalog_repository = workflow.resolve().parents[1]
    actual_skill = catalog_repository / "skill" / staged_skill.name
    replacements = {
        "${REPO_ROOT}": str(catalog_repository),
        "${SKILL_DIR}": str(actual_skill),
    }

    def replace_tokens(value: object) -> object:
        if isinstance(value, dict):
            return {key: replace_tokens(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_tokens(item) for item in value]
        if isinstance(value, str):
            for token, replacement in replacements.items():
                value = value.replace(token, replacement)
        return value

    config = json.loads(config_path.read_text(encoding="utf-8"))
    normalized = replace_tokens(config)
    config_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_staged_skill(staged_skill: Path, repository: Path) -> list[str]:
    """Run package-level checks before any selected file reaches the repository."""
    if not (staged_skill / "SKILL.md").is_file():
        raise StagedValidationError("staged package is missing SKILL.md")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["INUYASHA_SYNC_TOOL_PATH"] = str(Path(__file__).resolve())
    environment["INUYASHA_WORKFLOW_HOME"] = str(repository)
    environment["INUYASHA_WORKFLOW_ROOT"] = str(
        repository / "workflow/reference-workflow"
    )
    environment.pop("PYTHONPATH", None)
    python = validation_python(repository)
    validations = []
    compile_targets = [
        str(path)
        for path in (staged_skill / "scripts", staged_skill / "tests")
        if path.is_dir()
    ]
    validations.append(
        run_validation_command(
            "compileall",
            [str(python), "-m", "compileall", "-q", *compile_targets],
            repository,
            environment,
        )
    )
    tests = staged_skill / "tests"
    if tests.is_dir():
        validations.append(
            run_validation_command(
                "unit-tests",
                [
                    str(python),
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(tests),
                    "-p",
                    "test_*.py",
                ],
                repository,
                environment,
            )
        )
    validator = staged_skill / "scripts/validate_workflow.py"
    workflow = repository / "workflow/reference-workflow"
    if validator.is_file():
        if not workflow.is_dir():
            raise StagedValidationError(
                "package repository is missing workflow/reference-workflow"
            )
        normalize_staged_config_for_catalog(staged_skill, workflow)
        validations.append(
            run_validation_command(
                "workflow-validation",
                [
                    str(python),
                    str(validator),
                    "--workflow-root",
                    str(workflow),
                ],
                repository,
                environment,
            )
        )
    return validations


def create_backup_root(base: Path | None = None) -> Path:
    parent = (
        base
        if base is not None
        else Path.home() / ".codex/backups/inuyasha-art-workflow"
    )
    parent.mkdir(parents=True, exist_ok=True)
    prefix = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-")
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))


def verify_destination_unchanged(
    destination_root: Path, statuses: list[FileStatus]
) -> None:
    for item in statuses:
        relative = Path(item.path)
        destination = safe_join(
            destination_root, relative, "package destination"
        )
        current_hash = sha256(destination) if destination.is_file() else None
        if current_hash != item.destination_sha256:
            raise RuntimeError(
                f"package destination changed after preview: {item.path}"
            )


def commit_staged_files(
    staged_skill: Path,
    destination_root: Path,
    statuses: list[FileStatus],
    *,
    backup_base: Path | None = None,
    copy_file: Callable[[Path, Path], None] = atomic_copy,
) -> tuple[list[str], Path]:
    """Commit validated files with complete backup and rollback on partial failure."""
    verify_destination_unchanged(destination_root, statuses)
    backup_root = create_backup_root(backup_base)
    manifest = {"schema_version": 1, "files": []}
    for item in statuses:
        relative = Path(item.path)
        destination = safe_join(
            destination_root, relative, "package destination"
        )
        backup = safe_join(backup_root, relative, "backup")
        existed = destination.is_file()
        if existed:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
        manifest["files"].append(
            {
                "path": item.path,
                "existed": existed,
                "original_sha256": item.destination_sha256,
                "installed_sha256": item.source_sha256,
            }
        )
    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    applied: list[str] = []
    try:
        for item in statuses:
            relative = Path(item.path)
            staged = safe_join(staged_skill, relative, "staged package")
            destination = safe_join(
                destination_root, relative, "package destination"
            )
            copy_file(staged, destination)
            applied.append(item.path)
            if sha256(destination) != item.source_sha256:
                raise RuntimeError(f"post-copy hash mismatch: {item.path}")
    except Exception as exc:
        rollback_failures = []
        for item_path in reversed(applied):
            item = next(status for status in statuses if status.path == item_path)
            relative = Path(item.path)
            destination = safe_join(
                destination_root, relative, "package destination"
            )
            try:
                if item.destination_sha256 is None:
                    destination.unlink(missing_ok=True)
                else:
                    backup = safe_join(backup_root, relative, "backup")
                    atomic_copy(backup, destination)
            except (OSError, RuntimeError, ValueError) as rollback_exc:
                rollback_failures.append(f"{item.path}: {rollback_exc}")
        if rollback_failures:
            raise RuntimeError(
                f"package update failed ({exc}); rollback also failed: "
                + "; ".join(rollback_failures)
            ) from exc
        raise RuntimeError(f"package update failed and was rolled back: {exc}") from exc
    return applied, backup_root


def stage_validate_and_commit(
    repository: Path,
    source_root: Path,
    destination_root: Path,
    statuses: list[FileStatus],
    *,
    validator: Callable[[Path, Path], list[str]] = validate_staged_skill,
    backup_base: Path | None = None,
    copy_file: Callable[[Path, Path], None] = atomic_copy,
) -> tuple[list[str], Path, list[str]]:
    reject_tree_symlinks(destination_root, "package skill")
    with tempfile.TemporaryDirectory(prefix="inuyasha-package-stage-") as temporary:
        staged_repository = Path(temporary) / "repository"
        staged_skill = (
            staged_repository / "skill/generate-inuyasha-manga-art"
        )
        shutil.copytree(destination_root, staged_skill, symlinks=True)
        for name in ("workflow", "libraries"):
            source = repository / name
            if not source.is_dir():
                raise StagedValidationError(
                    f"package repository is missing required directory: {name}"
                )
            (staged_repository / name).symlink_to(
                source.resolve(), target_is_directory=True
            )
        for item in statuses:
            relative = Path(item.path)
            source = safe_join(source_root, relative, "installed source")
            staged = safe_join(staged_skill, relative, "staged package")
            atomic_copy(source, staged)
        validations = validator(staged_skill, repository)
        applied, backup_root = commit_staged_files(
            staged_skill,
            destination_root,
            statuses,
            backup_base=backup_base,
            copy_file=copy_file,
        )
    return applied, backup_root, validations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination-root", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Skill-relative file to inspect or apply; repeat for multiple files.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow named dirty targets after staged validation and unique backup.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    destination_root = args.destination_root.expanduser().resolve()
    if not source_root.is_dir():
        raise SystemExit(f"installed skill is missing: {source_root}")
    if not destination_root.is_dir():
        raise SystemExit(f"package skill is missing: {destination_root}")
    if source_root == destination_root:
        raise SystemExit("installed and package skill roots must be different")
    if source_root.is_relative_to(destination_root) or destination_root.is_relative_to(
        source_root
    ):
        raise SystemExit("installed and package skill roots must not contain each other")
    if args.allow_dirty and not args.apply:
        raise SystemExit("--allow-dirty is valid only with --apply")
    if args.apply and not args.include:
        raise SystemExit("--apply requires at least one explicit --include file")

    try:
        repository = repository_for(destination_root)
        relatives = selected_files(source_root, args.include)
        statuses = [
            inspect_file(repository, source_root, destination_root, relative)
            for relative in relatives
        ]
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    changed = [item for item in statuses if item.state != "identical"]
    blocked = [
        item
        for item in changed
        if item.protected or (item.dirty and not args.allow_dirty)
    ]
    applied: list[str] = []
    backup_root: Path | None = None
    validations: list[str] = []
    if args.apply:
        if blocked:
            reasons = ", ".join(
                f"{item.path} ({'protected' if item.protected else 'dirty'})"
                for item in blocked
            )
            raise SystemExit(f"refusing to overwrite: {reasons}")
        if changed:
            try:
                applied, backup_root, validations = stage_validate_and_commit(
                    repository, source_root, destination_root, changed
                )
            except (OSError, RuntimeError, ValueError) as exc:
                raise SystemExit(str(exc)) from exc

    result = {
        "mode": "apply" if args.apply else "preview",
        "source_root": str(source_root),
        "destination_root": str(destination_root),
        "inspected": len(statuses),
        "changed": len(changed),
        "blocked": [item.path for item in blocked],
        "validations": validations,
        "applied": applied,
        "backup_root": str(backup_root) if backup_root else None,
        "files": [asdict(item) for item in statuses if item.state != "identical"],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"{result['mode']}: inspected={result['inspected']} "
            f"changed={result['changed']} blocked={len(result['blocked'])}"
        )
        for item in changed:
            flags = []
            if item.protected:
                flags.append("protected")
            if item.dirty:
                flags.append("dirty")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            print(f"{item.state:9} {item.path}{suffix}")
        if validations:
            print("validated: " + ", ".join(validations))
        if applied:
            print("applied: " + ", ".join(applied))
        if backup_root:
            print(f"backup: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
