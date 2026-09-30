#!/usr/bin/env python3
"""Validate supplied CSV evidence and emit a provider-free estate proposal."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20000
REPO = re.compile(r"(?:\.github|[A-Za-z0-9][A-Za-z0-9_.-]{0,99})")
SNAPSHOT = "repo,archived,pushed,language,open_issues,license,description".split(",")
FILES = "pyproject.toml,requirements.txt,package.json,Dockerfile,.github/dependabot.yml,SECURITY.md,LICENSE".split(",")
CONSOLIDATION = "repo,proposed_tier,pushed,language,open_issues,license".split(",") + FILES
DEPENDENCIES = "ecosystem,package,repo,spec".split(",")
TIERS = {"service/library", "docs/public", "product", "flagship", "kernel/package", "bind-as-package"}


def read_csv(path: Path, header: list[str]) -> tuple[list[dict], dict]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or b"\0" in raw:
        raise ValueError("CSV size or NUL boundary rejected")
    csv.field_size_limit(16384)
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, None) != header:
        raise ValueError("exact case-sensitive CSV header required")
    rows = []
    for values in reader:
        if len(values) != len(header) or len(rows) >= MAX_ROWS:
            raise ValueError("CSV row shape or count rejected")
        rows.append(dict(zip(header, values)))
    if not rows:
        raise ValueError("empty CSV rejected")
    return rows, {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "rows": len(rows)}


def by_repo(rows: list[dict]) -> dict[str, dict]:
    result = {}
    folded = set()
    for row in rows:
        name = row["repo"]
        if not REPO.fullmatch(name) or name.casefold() in folded:
            raise ValueError("invalid or duplicate repository")
        if not row["open_issues"].isascii() or not row["open_issues"].isdigit():
            raise ValueError("open_issues must be a nonnegative ASCII integer")
        result[name] = row
        folded.add(name.casefold())
    return result


def proposal(snapshot: Path, consolidation: Path, dependencies: Path) -> dict:
    snapshots, snapshot_hash = read_csv(snapshot, SNAPSHOT)
    candidates, candidate_hash = read_csv(consolidation, CONSOLIDATION)
    declarations, dependency_hash = read_csv(dependencies, DEPENDENCIES)
    inventory, proposed = by_repo(snapshots), by_repo(candidates)
    for row in snapshots:
        if row["archived"] not in {"True", "False"}:
            raise ValueError("archived must be True or False")
    active = {name for name, row in inventory.items() if row["archived"] == "False"}
    if set(proposed) != active:
        raise ValueError("consolidation membership must equal snapshot active membership")
    for row in candidates:
        if row["proposed_tier"] not in TIERS or any(row[key] not in {"True", "False"} for key in FILES):
            raise ValueError("unknown tier or invalid file-existence boolean")
    groups = defaultdict(list)
    seen = set()
    for row in declarations:
        key = tuple(row[col] for col in DEPENDENCIES)
        if key in seen or row["repo"] not in active:
            raise ValueError("duplicate dependency row or inactive/unknown repository")
        if row["ecosystem"] not in {"python", "npm"} or not row["package"].strip():
            raise ValueError("unknown ecosystem or empty package")
        seen.add(key)
        groups[(row["ecosystem"], row["package"])].append({"repo": row["repo"], "spec": row["spec"]})
    drift = []
    for (ecosystem, package), rows in sorted(groups.items()):
        specs = sorted({row["spec"] for row in rows})
        if len(specs) > 1:
            drift.append({"ecosystem": ecosystem, "package": package, "specs": specs,
                          "declarations": sorted(rows, key=lambda r: (r["repo"], r["spec"]))})
    skew = []
    for name in sorted(active):
        for field in ("pushed", "language", "open_issues", "license"):
            if inventory[name][field] != proposed[name][field]:
                skew.append({"repo": name, "field": field, "snapshot": inventory[name][field],
                             "consolidation": proposed[name][field]})
    unpinned = [row for row in declarations if not row["spec"].strip()]
    entries = []
    for name, row in sorted(proposed.items()):
        entries.append({"repo": name, "tier": row["proposed_tier"], "parent": None,
                        "canonical_source": {"repository": f"szl-holdings/{name}", "sha": None},
                        "hf_targets": None, "demo": "NOT_MEASURED", "claims_file": None,
                        "status": "PROPOSED", "license_metadata": row["license"],
                        "license_review": "NOT_MEASURED",
                        "files": {key: row[key] == "True" for key in FILES}})
    return {"schema": "szl.estate-snapshot-proposal/v1", "status": "VALIDATED_PROPOSAL",
            "trust": "UNSIGNED_HONEST", "scope": "SUPPLIED_PUBLIC_SNAPSHOT",
            "production_authorization": False, "automatic_promotion_authorized": False,
            "inputs": {"snapshot": snapshot_hash, "consolidation": candidate_hash,
                       "dependencies": dependency_hash},
            "counts": {"repositories": len(inventory), "active": len(active),
                       "archived": len(inventory) - len(active), "dependency_rows": len(declarations),
                       "tier": dict(sorted(Counter(r["tier"] for r in entries).items())),
                       "spec_drift_packages": dict(sorted(Counter(r["ecosystem"] for r in drift).items()))},
            "metadata_skew": skew, "unpinned_declarations": unpinned,
            "spec_drift": drift, "repositories": entries,
            "limits": ["Spec drift is not a solved dependency conflict.",
                       "Membership equality compares supplied files, not current authenticated inventory.",
                       "File existence is not license review or runtime readiness.",
                       "Source SHAs, Hub targets, parents, demos and claims bindings remain unresolved.",
                       "No archive, package adoption, provider write or release is authorized."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "consolidation", "dependencies", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = proposal(args.snapshot, args.consolidation, args.dependencies)
        encoded = json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
        # Exclusive creation preserves prior evidence and prevents accidental input overwrite.
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        reason = str(error) if type(error) is ValueError else type(error).__name__
        print(json.dumps({"status": "REJECTED", "production_authorization": False, "reason": reason}))
        return 2
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "proposal_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
