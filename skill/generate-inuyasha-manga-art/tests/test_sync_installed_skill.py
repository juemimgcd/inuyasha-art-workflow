from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOL_PATH = Path(
    os.environ.get(
        "INUYASHA_SYNC_TOOL_PATH",
        Path(__file__).resolve().parents[3] / "tools/sync_installed_skill.py",
    )
)
SPEC = importlib.util.spec_from_file_location("sync_installed_skill_under_test", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load sync tool: {TOOL_PATH}")
sync_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_tool
SPEC.loader.exec_module(sync_tool)


class SyncInstalledSkillTests(unittest.TestCase):
    def make_repository_skeleton(self, repository: Path) -> None:
        (repository / "workflow/reference-workflow").mkdir(parents=True)
        (repository / "libraries").mkdir()

    def status_for(self, source: Path, destination: Path, relative: str):
        source_file = source / relative
        destination_file = destination / relative
        return sync_tool.FileStatus(
            path=relative,
            state="different" if destination_file.exists() else "missing",
            dirty=False,
            protected=False,
            source_sha256=sync_tool.sha256(source_file),
            destination_sha256=(
                sync_tool.sha256(destination_file)
                if destination_file.is_file()
                else None
            ),
        )

    def test_safe_join_rejects_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "destination"
            outside = root / "outside"
            destination.mkdir()
            outside.mkdir()
            (destination / "scripts").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                sync_tool.safe_join(
                    destination, Path("scripts/payload.txt"), "package destination"
                )

    def test_protected_path_matching_is_case_insensitive(self) -> None:
        self.assertTrue(
            sync_tool.is_protected(Path("REFERENCES/SOURCE-LIBRARY.JSON"))
        )
        self.assertFalse(sync_tool.is_protected(Path("references/other.json")))

    def test_staging_rejects_unselected_package_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            source = root / "installed"
            destination = repository / "skill/generate-inuyasha-manga-art"
            self.make_repository_skeleton(repository)
            source.mkdir(parents=True)
            destination.mkdir(parents=True)
            outside = root / "outside.py"
            outside.write_text("VALUE = 'outside'\n", encoding="utf-8")
            (destination / "unselected.py").symlink_to(outside)
            (destination / "SKILL.md").write_text("old\n", encoding="utf-8")
            (source / "SKILL.md").write_text("new\n", encoding="utf-8")
            status = self.status_for(source, destination, "SKILL.md")
            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                sync_tool.stage_validate_and_commit(
                    repository,
                    source,
                    destination,
                    [status],
                    validator=lambda _staged, _repository: ["not-reached"],
                    backup_base=root / "backups",
                )
            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"), "old\n"
            )

    def test_backup_roots_are_unique_within_one_second(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = sync_tool.create_backup_root(base)
            second = sync_tool.create_backup_root(base)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    def test_validation_python_preserves_virtualenv_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            entrypoint = repository / (
                ".venv/Scripts/python.exe"
                if os.name == "nt"
                else ".venv/bin/python"
            )
            entrypoint.parent.mkdir(parents=True)
            if os.name == "nt":
                entrypoint.symlink_to(Path(sys.executable))
            else:
                entrypoint.write_text(
                    f'#!/bin/sh\nexec "{sys.executable}" "$@"\n',
                    encoding="utf-8",
                )
                entrypoint.chmod(0o755)
            self.assertEqual(
                sync_tool.validation_python(repository), entrypoint.absolute()
            )

    def test_validation_python_skips_unlaunchable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            invalid = repository / (
                ".venv/Scripts/python.exe"
                if os.name == "nt"
                else ".venv/bin/python"
            )
            invalid.parent.mkdir(parents=True)
            invalid.write_text("not an executable", encoding="utf-8")
            success = sync_tool.subprocess.CompletedProcess([], 0)
            with (
                patch.object(
                    sync_tool,
                    "REPOSITORY_ROOT",
                    repository / "missing-tool-root",
                ),
                patch.object(
                    sync_tool.subprocess,
                    "run",
                    side_effect=[OSError("invalid executable"), success],
                ),
            ):
                self.assertEqual(
                    sync_tool.validation_python(repository),
                    Path(sys.executable).absolute(),
                )

    def test_staged_catalog_config_uses_catalog_owner_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_repository = root / "catalog-owner"
            workflow = catalog_repository / "workflow/reference-workflow"
            workflow.mkdir(parents=True)
            staged_skill = root / "stage/skill/generate-inuyasha-manga-art"
            config = staged_skill / "references/source-library.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"workflow_root":"${REPO_ROOT}/workflow/reference-workflow",'
                '"skill":"${SKILL_DIR}"}\n',
                encoding="utf-8",
            )
            sync_tool.normalize_staged_config_for_catalog(staged_skill, workflow)
            normalized_text = config.read_text(encoding="utf-8")
            normalized = json.loads(normalized_text)
            self.assertEqual(
                Path(normalized["workflow_root"]).resolve(), workflow.resolve()
            )
            self.assertEqual(
                Path(normalized["skill"]).resolve(),
                (
                    catalog_repository
                    / "skill/generate-inuyasha-manga-art"
                ).resolve(),
            )
            self.assertNotIn("${REPO_ROOT}", normalized_text)
            self.assertNotIn("${SKILL_DIR}", normalized_text)

    def test_incompatible_single_file_fails_before_repository_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            source = root / "installed"
            destination = repository / "skill/generate-inuyasha-manga-art"
            self.make_repository_skeleton(repository)
            (source / "scripts").mkdir(parents=True)
            (destination / "scripts").mkdir(parents=True)
            (destination / "tests").mkdir()
            (destination / "SKILL.md").write_text(
                "---\nname: fixture\ndescription: fixture\n---\n",
                encoding="utf-8",
            )
            (destination / "scripts/dep.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            current = destination / "scripts/main.py"
            current.write_text("VALUE = 1\n", encoding="utf-8")
            (source / "scripts/main.py").write_text(
                "from dep import MISSING\n", encoding="utf-8"
            )
            (destination / "tests/test_import.py").write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))\n"
                "from main import VALUE\n"
                "def test_value():\n"
                "    assert VALUE == 1\n",
                encoding="utf-8",
            )
            status = self.status_for(source, destination, "scripts/main.py")
            with self.assertRaisesRegex(
                sync_tool.StagedValidationError, "staged validation failed"
            ):
                sync_tool.stage_validate_and_commit(
                    repository,
                    source,
                    destination,
                    [status],
                    backup_base=root / "backups",
                )
            self.assertEqual(current.read_text(encoding="utf-8"), "VALUE = 1\n")
            self.assertFalse((root / "backups").exists())

    def test_partial_commit_rolls_back_already_written_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            staged = root / "staged"
            destination = root / "destination"
            for directory in (source, staged, destination):
                directory.mkdir()
            statuses = []
            for name in ("one.txt", "two.txt"):
                (source / name).write_text(f"new-{name}\n", encoding="utf-8")
                (staged / name).write_text(f"new-{name}\n", encoding="utf-8")
                (destination / name).write_text(f"old-{name}\n", encoding="utf-8")
                statuses.append(self.status_for(source, destination, name))

            calls = 0

            def fail_second_copy(copy_source: Path, copy_destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated second-file failure")
                sync_tool.atomic_copy(copy_source, copy_destination)

            with self.assertRaisesRegex(RuntimeError, "was rolled back"):
                sync_tool.commit_staged_files(
                    staged,
                    destination,
                    statuses,
                    backup_base=root / "backups",
                    copy_file=fail_second_copy,
                )
            self.assertEqual(
                (destination / "one.txt").read_text(encoding="utf-8"),
                "old-one.txt\n",
            )
            self.assertEqual(
                (destination / "two.txt").read_text(encoding="utf-8"),
                "old-two.txt\n",
            )

    def test_validated_change_is_applied_with_manifest_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            source = root / "installed"
            destination = repository / "skill/generate-inuyasha-manga-art"
            self.make_repository_skeleton(repository)
            source.mkdir(parents=True)
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("old\n", encoding="utf-8")
            (source / "SKILL.md").write_text("new\n", encoding="utf-8")
            status = self.status_for(source, destination, "SKILL.md")
            applied, backup, validations = sync_tool.stage_validate_and_commit(
                repository,
                source,
                destination,
                [status],
                validator=lambda _staged, _repository: ["fixture-validation"],
                backup_base=root / "backups",
            )
            self.assertEqual(applied, ["SKILL.md"])
            self.assertEqual(validations, ["fixture-validation"])
            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"), "new\n"
            )
            self.assertEqual((backup / "SKILL.md").read_text(), "old\n")
            self.assertTrue((backup / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
