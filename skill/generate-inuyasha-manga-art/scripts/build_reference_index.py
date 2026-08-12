#!/usr/bin/env python3
"""Build an atomic SQLite inventory of the local Inuyasha reference library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from workflow_common import (
    IMAGE_EXTENSIONS,
    LEGACY_ALIASES_PATH,
    atomic_write_json,
    annotation_shot_types,
    eligible_reference_roles,
    ensure_workflow_dirs,
    folder_metadata,
    infer_structured_metadata,
    infer_tags,
    legacy_file_item_id,
    library_signature,
    load_annotations,
    load_config,
    load_json,
    now_iso,
    source_config_fingerprint,
    stable_file_item_id,
    visible_files,
    workflow_root,
)

SCHEMA_VERSION = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-root", type=Path)
    parser.add_argument("--force", action="store_true", help="Rebuild even when fresh.")
    parser.add_argument(
        "--rehash",
        action="store_true",
        help="Recompute hashes and dimensions instead of reusing unchanged-file cache.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check freshness only; exit 3 when missing or stale.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable status."
    )
    return parser.parse_args()


def read_meta(database: Path) -> dict[str, str]:
    if not database.is_file():
        return {}
    try:
        connection = sqlite3.connect(database)
        rows = connection.execute("SELECT key, value FROM meta").fetchall()
        connection.close()
        return dict(rows)
    except sqlite3.Error:
        return {}


def annotations_fingerprint(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freshness(
    database: Path,
    config: dict[str, Any],
    signature: dict[str, Any],
    annotations_path: Path,
) -> tuple[bool, str]:
    meta = read_meta(database)
    if not meta:
        return False, "catalog missing or unreadable"
    if meta.get("schema_version") != str(SCHEMA_VERSION):
        return False, "catalog schema changed"
    if meta.get("config_fingerprint") != source_config_fingerprint(config):
        return False, "source configuration changed"
    try:
        stored_signature = json.loads(meta.get("library_signature", "{}"))
    except json.JSONDecodeError:
        return False, "stored signature is invalid"
    if stored_signature != signature:
        return False, "source library changed"
    if meta.get("annotations_fingerprint") != annotations_fingerprint(annotations_path):
        return False, "local annotations changed"
    if meta.get("legacy_aliases_fingerprint") != annotations_fingerprint(
        LEGACY_ALIASES_PATH
    ):
        return False, "legacy alias map changed"
    return True, "catalog is fresh"


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except (ImportError, OSError):
        return None, None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_image_cache(database: Path) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    """Load reusable hash and dimension data from a schema-v2 catalog."""
    if not database.is_file():
        return {}
    try:
        connection = sqlite3.connect(database)
        item_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(items)").fetchall()
        }
        has_locations = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_locations'"
        ).fetchone()
        if "content_hash" not in item_columns or not has_locations:
            connection.close()
            return {}
        rows = connection.execute(
            """
            SELECT locations.source_id, locations.relative_path,
                   locations.size_bytes, locations.mtime_ns,
                   items.content_hash, items.width, items.height
            FROM item_locations AS locations
            JOIN items ON items.item_id = locations.item_id
            WHERE items.kind = 'image'
            """
        ).fetchall()
        connection.close()
    except sqlite3.Error:
        return {}
    return {
        (row[0], row[1], row[2], row[3]): {
            "content_hash": row[4],
            "width": row[5],
            "height": row[6],
        }
        for row in rows
    }


def load_alias_cache(database: Path) -> list[tuple[str, str, str]]:
    """Carry path aliases forward so repeated folder moves remain resolvable."""
    if not database.is_file():
        return []
    try:
        connection = sqlite3.connect(database)
        has_aliases = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_aliases'"
        ).fetchone()
        if not has_aliases:
            connection.close()
            return []
        rows = connection.execute(
            "SELECT alias_id, item_id, reason FROM item_aliases"
        ).fetchall()
        connection.close()
        return rows
    except sqlite3.Error:
        return []


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = DELETE;
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE sources (
            source_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            root_path TEXT NOT NULL,
            source_type TEXT NOT NULL,
            medium TEXT NOT NULL,
            authority TEXT NOT NULL,
            evidence_roles TEXT NOT NULL,
            exists_flag INTEGER NOT NULL
        );
        CREATE TABLE items (
            item_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(source_id),
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            content_hash TEXT,
            folder_path TEXT NOT NULL DEFAULT '',
            content_label TEXT NOT NULL DEFAULT '',
            folder_tags TEXT NOT NULL DEFAULT '[]',
            subjects TEXT NOT NULL DEFAULT '[]',
            forms TEXT NOT NULL DEFAULT '[]',
            subject_forms TEXT NOT NULL DEFAULT '{}',
            shot_types TEXT NOT NULL DEFAULT '[]',
            filename_terms TEXT NOT NULL DEFAULT '[]',
            duplicate_count INTEGER NOT NULL DEFAULT 1,
            extension TEXT,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            width INTEGER,
            height INTEGER,
            volume INTEGER,
            pdf_page INTEGER,
            page_count INTEGER,
            curated INTEGER NOT NULL DEFAULT 0,
            eligible_roles TEXT NOT NULL DEFAULT '[]',
            tags TEXT NOT NULL,
            note TEXT NOT NULL,
            search_text TEXT NOT NULL
        );
        CREATE INDEX idx_items_source ON items(source_id);
        CREATE INDEX idx_items_kind ON items(kind);
        CREATE INDEX idx_items_volume_page ON items(volume, pdf_page);
        CREATE INDEX idx_items_curated ON items(curated);
        CREATE INDEX idx_items_content_hash ON items(content_hash);
        CREATE INDEX idx_items_content_label ON items(content_label);
        CREATE TABLE item_locations (
            item_id TEXT NOT NULL REFERENCES items(item_id),
            source_id TEXT NOT NULL,
            path TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            content_label TEXT NOT NULL,
            folder_tags TEXT NOT NULL,
            subjects TEXT NOT NULL DEFAULT '[]',
            forms TEXT NOT NULL DEFAULT '[]',
            subject_forms TEXT NOT NULL DEFAULT '{}',
            shot_types TEXT NOT NULL DEFAULT '[]',
            filename_terms TEXT NOT NULL DEFAULT '[]',
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            PRIMARY KEY (item_id, relative_path)
        );
        CREATE INDEX idx_locations_source ON item_locations(source_id);
        CREATE INDEX idx_locations_relative ON item_locations(relative_path);
        CREATE TABLE item_aliases (
            alias_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES items(item_id),
            reason TEXT NOT NULL
        );
        CREATE INDEX idx_aliases_item ON item_aliases(item_id);
        """
    )


def insert_item(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    row = {
        "folder_path": "",
        "content_label": "",
        "folder_tags": "[]",
        "subjects": "[]",
        "forms": "[]",
        "subject_forms": "{}",
        "shot_types": "[]",
        "filename_terms": "[]",
        "duplicate_count": 1,
        "eligible_roles": "[]",
        **row,
    }
    columns = (
        "item_id",
        "source_id",
        "kind",
        "path",
        "relative_path",
        "content_hash",
        "folder_path",
        "content_label",
        "folder_tags",
        "subjects",
        "forms",
        "subject_forms",
        "shot_types",
        "filename_terms",
        "duplicate_count",
        "extension",
        "size_bytes",
        "mtime_ns",
        "width",
        "height",
        "volume",
        "pdf_page",
        "page_count",
        "curated",
        "eligible_roles",
        "tags",
        "note",
        "search_text",
    )
    connection.execute(
        f"INSERT INTO items ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [row.get(column) for column in columns],
    )


def insert_location(connection: sqlite3.Connection, row: dict[str, Any]) -> None:
    columns = (
        "item_id",
        "source_id",
        "path",
        "relative_path",
        "folder_path",
        "content_label",
        "folder_tags",
        "subjects",
        "forms",
        "subject_forms",
        "shot_types",
        "filename_terms",
        "size_bytes",
        "mtime_ns",
    )
    connection.execute(
        f"INSERT INTO item_locations ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)})",
        [row.get(column) for column in columns],
    )


def apply_annotations(
    item_ids: list[str],
    tags: set[str],
    note: str,
    annotations: dict[str, dict[str, Any]],
) -> tuple[set[str], str, bool]:
    annotated = False
    for item_id in item_ids:
        annotation = annotations.get(item_id)
        if not annotation:
            continue
        annotated = True
        tags.update(annotation.get("tags", []))
        if annotation.get("note"):
            note = annotation["note"]
    return tags, note, annotated


def build_database(
    temporary: Path,
    previous_database: Path,
    config: dict[str, Any],
    signature: dict[str, Any],
    annotations_path: Path,
    rehash: bool = False,
) -> dict[str, Any]:
    if temporary.exists():
        temporary.unlink()
    annotations = load_annotations(annotations_path)
    connection = sqlite3.connect(temporary)
    create_schema(connection)
    counts: Counter[str] = Counter()
    source_counts: dict[str, Counter[str]] = {}
    image_cache = {} if rehash else load_image_cache(previous_database)
    cache_hits = 0
    hash_computations = 0

    for source in config["sources"]:
        source_id = source["id"]
        root = Path(source["path"])
        connection.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                source["label"],
                str(root),
                source["source_type"],
                source["medium"],
                source["authority"],
                json.dumps(source.get("evidence_roles", []), ensure_ascii=False),
                int(root.is_dir()),
            ),
        )
        per_source: Counter[str] = Counter()
        source_counts[source_id] = per_source
        if not root.is_dir():
            continue

        source_files = sorted(
            visible_files(root, source.get("exclude_globs", [])),
            key=lambda item: str(item).casefold(),
        )
        if source["source_type"] == "image-directory":
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for path in source_files:
                extension = path.suffix.lower()
                if extension not in IMAGE_EXTENSIONS:
                    continue
                relative = str(path.relative_to(root))
                relative_path = Path(relative)
                stat = path.stat()
                cache_key = (source_id, relative, stat.st_size, stat.st_mtime_ns)
                cached = image_cache.get(cache_key)
                if cached:
                    digest = cached["content_hash"]
                    width, height = cached["width"], cached["height"]
                    cache_hits += 1
                else:
                    digest = file_sha256(path)
                    width, height = image_dimensions(path)
                    hash_computations += 1
                folder_path, content_label, folder_tags = folder_metadata(relative_path)
                structured = infer_structured_metadata(relative_path, source)
                grouped[digest].append(
                    {
                        "path": path,
                        "relative_path": relative,
                        "extension": extension,
                        "size_bytes": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "width": width,
                        "height": height,
                        "folder_path": folder_path,
                        "content_label": content_label,
                        "folder_tags": folder_tags,
                        **structured,
                    }
                )

            for digest, locations in sorted(grouped.items()):
                locations.sort(key=lambda row: row["relative_path"].casefold())
                canonical = locations[0]
                item_id = stable_file_item_id(source_id, digest)
                tags = set(source.get("default_tags", []))
                annotation_ids = [item_id]
                for location in locations:
                    relative_path = Path(location["relative_path"])
                    tags.update(infer_tags(relative_path, source))
                    annotation_ids.append(
                        legacy_file_item_id(source_id, location["relative_path"])
                    )
                tags, note, annotated = apply_annotations(
                    annotation_ids, tags, "", annotations
                )
                eligible_roles = eligible_reference_roles(
                    source.get("evidence_roles", []), tags
                )
                folder_tags = sorted(
                    {
                        folder_tag
                        for location in locations
                        for folder_tag in location["folder_tags"]
                    },
                    key=str.casefold,
                )
                structured_fields = {
                    field: sorted(
                        {value for location in locations for value in location[field]},
                        key=str.casefold,
                    )
                    for field in ("subjects", "forms", "shot_types", "filename_terms")
                }
                subject_forms: dict[str, set[str]] = defaultdict(set)
                for location in locations:
                    for subject, forms in location["subject_forms"].items():
                        subject_forms[subject].update(forms)
                structured_subject_forms = {
                    subject: sorted(forms, key=str.casefold)
                    for subject, forms in sorted(
                        subject_forms.items(), key=lambda item: item[0].casefold()
                    )
                }
                structured_fields["shot_types"] = sorted(
                    set(structured_fields["shot_types"]) | annotation_shot_types(tags),
                    key=str.casefold,
                )
                search_text = " ".join(
                    [
                        source_id,
                        source["label"],
                        *(location["relative_path"] for location in locations),
                        *(location["folder_path"] for location in locations),
                        *(location["content_label"] for location in locations),
                        *folder_tags,
                        *(
                            value
                            for field in structured_fields.values()
                            for value in field
                        ),
                        *(
                            f"{subject}:{form}"
                            for subject, forms in structured_subject_forms.items()
                            for form in forms
                        ),
                        *sorted(tags),
                        note,
                    ]
                ).casefold()
                insert_item(
                    connection,
                    {
                        "item_id": item_id,
                        "source_id": source_id,
                        "kind": "image",
                        "path": str(canonical["path"]),
                        "relative_path": canonical["relative_path"],
                        "content_hash": digest,
                        "folder_path": canonical["folder_path"],
                        "content_label": canonical["content_label"],
                        "folder_tags": json.dumps(folder_tags, ensure_ascii=False),
                        **{
                            field: json.dumps(values, ensure_ascii=False)
                            for field, values in structured_fields.items()
                        },
                        "subject_forms": json.dumps(
                            structured_subject_forms, ensure_ascii=False
                        ),
                        "duplicate_count": len(locations),
                        "extension": canonical["extension"],
                        "size_bytes": canonical["size_bytes"],
                        "mtime_ns": canonical["mtime_ns"],
                        "width": canonical["width"],
                        "height": canonical["height"],
                        "curated": int(source_id.endswith("curated") or annotated),
                        "eligible_roles": json.dumps(
                            eligible_roles, ensure_ascii=False
                        ),
                        "tags": json.dumps(sorted(tags), ensure_ascii=False),
                        "note": note,
                        "search_text": search_text,
                    },
                )
                for location in locations:
                    insert_location(
                        connection,
                        {
                            "item_id": item_id,
                            "source_id": source_id,
                            **location,
                            "path": str(location["path"]),
                            "folder_tags": json.dumps(
                                location["folder_tags"], ensure_ascii=False
                            ),
                            "subjects": json.dumps(
                                location["subjects"], ensure_ascii=False
                            ),
                            "forms": json.dumps(location["forms"], ensure_ascii=False),
                            "subject_forms": json.dumps(
                                location["subject_forms"], ensure_ascii=False
                            ),
                            "shot_types": json.dumps(
                                location["shot_types"], ensure_ascii=False
                            ),
                            "filename_terms": json.dumps(
                                location["filename_terms"], ensure_ascii=False
                            ),
                        },
                    )
                    legacy_id = legacy_file_item_id(
                        source_id, location["relative_path"]
                    )
                    connection.execute(
                        "INSERT OR REPLACE INTO item_aliases VALUES (?, ?, ?)",
                        (legacy_id, item_id, "schema-v1-path-id"),
                    )
                counts["image"] += 1
                counts["image_file"] += len(locations)
                counts["duplicate_image_file"] += len(locations) - 1
                per_source["image"] += 1
                per_source["image_file"] += len(locations)
                per_source["duplicate_image_file"] += len(locations) - 1
            continue

    for alias_id, target_id, reason in load_alias_cache(previous_database):
        target_exists = connection.execute(
            "SELECT 1 FROM items WHERE item_id = ?", (target_id,)
        ).fetchone()
        if target_exists:
            connection.execute(
                "INSERT OR IGNORE INTO item_aliases VALUES (?, ?, ?)",
                (alias_id, target_id, reason),
            )

    if LEGACY_ALIASES_PATH.is_file():
        legacy_manifest = load_json(LEGACY_ALIASES_PATH)
        for alias in legacy_manifest.get("aliases", []):
            target_exists = connection.execute(
                "SELECT 1 FROM items WHERE item_id = ?", (alias["item_id"],)
            ).fetchone()
            if target_exists:
                connection.execute(
                    "INSERT OR REPLACE INTO item_aliases VALUES (?, ?, ?)",
                    (alias["alias_id"], alias["item_id"], alias["reason"]),
                )

    metadata = {
        "schema_version": str(SCHEMA_VERSION),
        "built_at": now_iso(),
        "config_fingerprint": source_config_fingerprint(config),
        "library_signature": json.dumps(signature, ensure_ascii=False, sort_keys=True),
        "annotations_fingerprint": annotations_fingerprint(annotations_path),
        "legacy_aliases_fingerprint": annotations_fingerprint(LEGACY_ALIASES_PATH),
    }
    connection.executemany("INSERT INTO meta VALUES (?, ?)", metadata.items())
    connection.commit()
    connection.execute("PRAGMA integrity_check").fetchone()
    connection.close()
    return {
        "built_at": metadata["built_at"],
        "database": str(temporary),
        "counts": dict(counts),
        "sources": {key: dict(value) for key, value in source_counts.items()},
        "library_signature": signature,
        "annotation_count": len(annotations),
        "incremental_cache": {
            "hash_cache_hits": cache_hits,
            "hash_computations": hash_computations,
            "rehash_requested": rehash,
        },
    }


def main() -> int:
    args = parse_args()
    config = load_config()
    root = workflow_root(config, args.workflow_root)
    paths = ensure_workflow_dirs(root)
    signature = library_signature(config)
    fresh, reason = freshness(
        paths["database"], config, signature, paths["annotations"]
    )
    status = {"fresh": fresh, "reason": reason, "database": str(paths["database"])}

    if args.check:
        print(json.dumps(status, ensure_ascii=False, indent=2) if args.json else reason)
        return 0 if fresh else 3

    if fresh and not args.force:
        print(json.dumps(status, ensure_ascii=False, indent=2) if args.json else reason)
        return 0

    temporary = paths["database"].with_name(
        f".{paths['database'].name}.building-{os.getpid()}"
    )
    try:
        summary = build_database(
            temporary,
            paths["database"],
            config,
            signature,
            paths["annotations"],
            rehash=args.rehash,
        )
        os.replace(temporary, paths["database"])
    finally:
        if temporary.exists():
            temporary.unlink()
    summary["database"] = str(paths["database"])
    atomic_write_json(paths["summary"], summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Built {paths['database']}")
        print(json.dumps(summary["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
