from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[1] / "scripts/run-python"


@unittest.skipIf(os.name == "nt", "POSIX launcher test")
class PosixRuntimeLauncherTests(unittest.TestCase):
    def make_python_stub(self, path: Path, pillow_available: bool) -> None:
        import_result = 0 if pillow_available else 87
        path.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = '-c' ] && [ \"${2:-}\" = 'import PIL' ]; then\n"
            f"  exit {import_result}\n"
            "fi\n"
            f'exec "{sys.executable}" "$@"\n',
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_explicit_interpreter_with_pillow_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stub = Path(temporary) / "python"
            self.make_python_stub(stub, pillow_available=True)
            environment = os.environ.copy()
            environment["INUYASHA_PYTHON"] = str(stub)
            process = subprocess.run(
                [str(LAUNCHER), "-c", "print('selected-project-python')"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout.strip(), "selected-project-python")

    def test_explicit_interpreter_without_pillow_fails_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stub = Path(temporary) / "python"
            self.make_python_stub(stub, pillow_available=False)
            environment = os.environ.copy()
            environment["INUYASHA_PYTHON"] = str(stub)
            process = subprocess.run(
                [str(LAUNCHER), "-c", "print('must-not-run')"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertNotIn("must-not-run", process.stdout)
            self.assertIn("cannot import Pillow", process.stderr)
            self.assertIn("No package was installed automatically", process.stderr)

    def test_missing_explicit_interpreter_fails_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing-python"
            environment = os.environ.copy()
            environment["INUYASHA_PYTHON"] = str(missing)
            process = subprocess.run(
                [str(LAUNCHER), "-c", "print('must-not-run')"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertNotIn("must-not-run", process.stdout)
            self.assertIn("is not executable", process.stderr)


if __name__ == "__main__":
    unittest.main()
