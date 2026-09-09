#!/usr/bin/env python3
"""Record installed bytes and plan source upgrades without overwriting local changes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from workflow_common import atomic_write_json, now_iso

SKILL_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PREFIX = "skill/generate-inuyasha-manga-art/"
PROVENANCE_FILE = ".runtime-provenance.json"
LOCAL_CONFIG = "references/source-library.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def managed(name: str) -> bool:
    path = Path(name)
    return (
        not any(part.startswith(".") or part == "__pycache__" for part in path.parts)
        and path.suffix not in {".pyc", ".pyo"}
        and (name == "SKILL.md" or path.parts[0] in {"scripts", "references", "agents", "tests"})
        and name != LOCAL_CONFIG
    )


def installed_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
        and managed(path.relative_to(root).as_posix())
    }


def fingerprint(files: dict[str, str]) -> str:
    return digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def source_files(repo: Path, revision: str) -> tuple[str, dict[str, str]]:
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{revision}^{{commit}}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", commit, PACKAGE_PREFIX.rstrip("/")],
        check=True, capture_output=True,
    ).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle:
            if member.isfile() and member.name.startswith(PACKAGE_PREFIX):
                name = member.name[len(PACKAGE_PREFIX):]
                if managed(name):
                    handle = bundle.extractfile(member)
                    if handle is not None:
                        files[name] = digest(handle.read())
    if not files:
        raise ValueError("revision contains no managed skill files")
    return commit, files


def runtime_record(root: Path = SKILL_ROOT) -> dict:
    files = installed_files(root)
    marker = root / PROVENANCE_FILE
    baseline = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    captured = baseline.get("installed_files", {})
    drift = sorted(name for name in files.keys() | captured.keys() if files.get(name) != captured.get(name))
    source = baseline.get("source_files", {})
    overrides = sorted(name for name in files.keys() | source.keys() if files.get(name) != source.get(name))
    config = root / LOCAL_CONFIG
    config_hash = digest(config.read_bytes()) if config.is_file() else None
    config_changed = bool(baseline) and baseline.get("source_library_sha256") != config_hash
    return {
        "schema_version": 1,
        "runtime_root": str(root),
        "fingerprint": fingerprint(files),
        "source_revision": baseline.get("source_revision") if source and not overrides else None,
        "comparison_revision": baseline.get("source_revision"),
        "source_repository": baseline.get("source_repository"),
        "state": "untracked" if not baseline else "modified-since-record" if drift or config_changed else "recorded-mixed" if overrides else "recorded",
        "matches_source_revision": bool(source) and not overrides,
        "differences_from_comparison": overrides if baseline else [],
        "difference_origin": "unknown-until-reviewed" if overrides else None,
        "changed_since_record": drift if baseline else [],
        "provenance_sha256": digest(marker.read_bytes()) if marker.is_file() else None,
        "source_library_sha256": config_hash,
        "configuration_changed_since_record": config_changed,
    }


def upgrade_plan(root: Path, incoming: dict[str, str]) -> list[dict]:
    marker = root / PROVENANCE_FILE
    if not marker.is_file():
        raise ValueError("record the current installation before planning an upgrade")
    baseline = json.loads(marker.read_text(encoding="utf-8"))
    base = baseline["source_files"]
    captured = baseline["installed_files"]
    local = installed_files(root)
    rows = []
    for name in sorted(base.keys() | incoming.keys() | local.keys()):
        old, current, new = base.get(name), local.get(name), incoming.get(name)
        action = (
            "unchanged" if current == new else
            "review-existing-difference" if old == new and current == captured.get(name) else
            "keep-local" if old == new else
            "remove-upstream" if current == old and new is None else
            "update" if current == old else "conflict"
        )
        if action != "unchanged":
            rows.append({"path": name, "action": action, "base_sha256": old,
                         "installed_sha256": current, "incoming_sha256": new})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "record", "plan-upgrade"))
    parser.add_argument("--skill-root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.skill_root.expanduser().resolve()
    try:
        if args.command == "status":
            result = runtime_record(root)
        else:
            if args.source_repo is None:
                parser.error("--source-repo is required for record and plan-upgrade")
            repo = args.source_repo.expanduser().resolve()
            commit, source = source_files(repo, args.revision)
            if args.command == "record":
                files = installed_files(root)
                marker = root / PROVENANCE_FILE
                if marker.is_file():
                    previous = marker.read_bytes()
                    archive = root / ".runtime-history" / f"{digest(previous)}.json"
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    if not archive.exists():
                        archive.write_bytes(previous)
                atomic_write_json(marker, {
                    "schema_version": 1, "recorded_at": now_iso(),
                    "source_repository": str(repo), "source_revision": commit,
                    "source_files": source, "installed_files": files,
                    "installed_fingerprint": fingerprint(files),
                    "source_library_sha256": digest((root / LOCAL_CONFIG).read_bytes()) if (root / LOCAL_CONFIG).is_file() else None,
                    "baseline_kind": "inventory-with-comparison-revision; installation-origin-not-asserted",
                })
                result = runtime_record(root)
            else:
                rows = upgrade_plan(root, source)
                result = {
                    "source_revision": commit, "changes": rows,
                    "conflicts": [row["path"] for row in rows if row["action"] == "conflict"],
                    "protected": [LOCAL_CONFIG], "applied": False,
                    "note": "Read-only plan. Review conflicts and stage named files with backup and validation before installation.",
                }
        if args.output:
            atomic_write_json(args.output.expanduser().resolve(), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"Runtime provenance failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
