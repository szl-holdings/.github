#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Copy the declared organization-card source files into a local browser fixture.

The canonical publisher independently validates and materializes the release.
This fixture has no Hub client, token handling, or publication capability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def prepare(root: Path, destination: Path) -> dict:
    root = root.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("preview destination must not already exist")
    manifest = json.loads((root / "huggingface/org-card.manifest.json").read_text())
    files = []
    targets = set()
    for entry in manifest["files"]:
        source = PurePosixPath(entry["source"])
        target = PurePosixPath(entry["destination"])
        if any(path.is_absolute() or ".." in path.parts or "\\" in str(path)
               for path in (source, target)) or str(target) in targets:
            raise ValueError("invalid or duplicate preview path")
        source_path = root / str(source)
        if source_path.is_symlink() or not source_path.resolve().is_relative_to(root):
            raise ValueError("preview source escapes repository")
        raw = source_path.read_bytes()
        files.append((str(source), str(target), raw))
        targets.add(str(target))
    if "index.html" not in targets or "assets/szl-mark-holographic.svg" not in targets:
        raise ValueError("preview omits the front door or shared mark")
    destination.mkdir(parents=True)
    record = []
    for source, target, raw in files:
        output = destination / target
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        record.append({"source": source, "destination": target,
                       "sha256": hashlib.sha256(raw).hexdigest()})
    return {"schema": "szl.org-card-source-preview/v1", "scope": "SOURCE_FILES_ONLY",
            "publication": False, "files": record}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.root, args.site)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f'org-card preview: {len(report["files"])} exact source files copied locally')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
