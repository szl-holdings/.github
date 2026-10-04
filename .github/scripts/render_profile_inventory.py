#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind public counters to one validated four-namespace source observation.

Refresh with --manifest, --source-revision and --source-git-blob. Subsequent
--check runs are offline and compare every generated paragraph and counter to
the committed binding. The estate release verifier independently reads the
immutable GitHub source and checks its bytes against this binding.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
KINDS = ("models", "datasets", "spaces", "kernels")
TYPES = dict(zip(KINDS, ("model", "dataset", "space", "kernel")))
SCOPE = {
    "id": "hf-public-author-membership/v2",
    "visibility": "public-only",
    "authentication": "none",
    "kinds": list(KINDS),
    "include_gated_metadata": True,
    "include_disabled_metadata": True,
    "include_reserved_readme_if_public": True,
    "kernel_policy": "native-kernel-namespace-separate-from-model-namespace",
    "identity_key": ["kind", "id"],
    "cross_namespace_ids": "may-overlap-not-a-unique-project-or-trained-model-total",
    "collections_and_buckets": "outside-repository-membership-scope",
    "portfolio_and_operational_policy": False,
}
START = "<!-- szl:public-inventory:start -->"
END = "<!-- szl:public-inventory:end -->"
SOURCE_PATH = "docs/huggingface-ecosystem-manifest.json"
SOURCE_REPO = "szl-holdings/a11oy"
BINDING_URL = "https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json"


class InventoryError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def timestamp(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
        raise InventoryError("observation must have a UTC timestamp")
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InventoryError("invalid observation date") from exc
    return value


def validate_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(KINDS):
        raise InventoryError("counts must contain all four native namespaces")
    if any(type(value[k]) is not int or value[k] < 0 for k in KINDS):
        raise InventoryError("counts must be non-negative integers")
    return value


def make_binding(raw: bytes, revision: str, blob: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise InventoryError("source revision must be an immutable commit")
    actual_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != actual_blob:
        raise InventoryError("source git blob does not match manifest bytes")
    manifest = json.loads(raw)
    counts = validate_counts(manifest.get("counts"))
    if manifest.get("org") != "SZLHOLDINGS" or set(manifest.get("inventory", {})) != set(KINDS):
        raise InventoryError("source manifest must enumerate all SZLHOLDINGS namespaces")
    scope = manifest.get("inventoryScope", {})
    if (scope.get("visibility") != "public-only" or scope.get("authenticated") is not False
            or scope.get("privateAssetsIncluded") is not False):
        raise InventoryError("source is not an anonymous public inventory")
    for kind in KINDS:
        rows = manifest["inventory"][kind]
        if not isinstance(rows, list) or len(rows) != counts[kind]:
            raise InventoryError(f"{kind}: count and membership disagree")
        seen = set()
        for row in rows:
            identifier = row.get("id") if isinstance(row, dict) else None
            if (not isinstance(identifier, str)
                    or not re.fullmatch(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9._-]*", identifier)
                    or row.get("private") is not False or row.get("repoType") != TYPES[kind]
                    or identifier in seen):
                raise InventoryError(f"{kind}: invalid, private, or duplicate source member")
            seen.add(identifier)
    return {
        "schema": "szl.public-profile-inventory/v1",
        "counts": counts,
        "observed_at": timestamp(manifest.get("observedAt")),
        "scope": SCOPE,
        "scope_sha256": canonical_sha256(SCOPE),
        "source_repository": SOURCE_REPO,
        "source_path": SOURCE_PATH,
        "source_revision": revision,
        "source_git_blob": blob,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "historical_portfolio_contract_replaced": False,
        "production_authorization": False,
        "runtime_readiness_inferred": False,
        "model_quality_inferred": False,
    }


def validate_binding(record: dict) -> None:
    validate_counts(record.get("counts"))
    timestamp(record.get("observed_at"))
    if record.get("scope") != SCOPE or record.get("scope_sha256") != canonical_sha256(SCOPE):
        raise InventoryError("binding predicate is not the four-namespace public contract")
    for key, length in (("source_revision", 40), ("source_git_blob", 40), ("source_sha256", 64)):
        if not isinstance(record.get(key), str) or not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", record[key]):
            raise InventoryError(f"invalid {key}")
    if (record.get("schema") != "szl.public-profile-inventory/v1"
            or record.get("source_repository") != SOURCE_REPO or record.get("source_path") != SOURCE_PATH
            or any(record.get(k) is not False for k in ("production_authorization",
                "runtime_readiness_inferred", "model_quality_inferred", "historical_portfolio_contract_replaced"))):
        raise InventoryError("binding source or claim boundary changed")


def count_line(record: dict) -> str:
    c = record["counts"]
    return (f'{c["spaces"]} public Spaces, {c["models"]} model repositories, '
            f'{c["kernels"]} native kernels, {c["datasets"]} datasets')


def source_url(record: dict) -> str:
    return f'https://github.com/{SOURCE_REPO}/blob/{record["source_revision"]}/{SOURCE_PATH}'


def markdown(record: dict) -> str:
    return (f'The source-bound public inventory records **{count_line(record)}** at '
            f'**{record["observed_at"]}** under `{record["scope"]["id"]}`. This is a dated observation, '
            'not a live count. Native kernel IDs may also appear in the model namespace; these '
            'figures do not count unique projects or trained language models. '
            f'[Inventory binding]({BINDING_URL}) · [Exact source]({source_url(record)}) · '
            '[Current Hub listing](https://huggingface.co/SZLHOLDINGS). '
            'Hub inventory is registry evidence, not availability, operational readiness, or publication policy. '
            'It does not establish model quality.')


def static(record: dict) -> str:
    labels = (("spaces", "public Spaces"), ("models", "model repositories"),
              ("kernels", "native kernels"), ("datasets", "public datasets"))
    observed = html.escape(record["observed_at"])
    rows = '\n'.join(f'<li data-szl-inventory-kind="{kind}"><strong>{record["counts"][kind]}</strong>'
                     f'<span>{label}</span></li>' for kind, label in labels)
    return (f'<ul class="szl-hf-counts" aria-label="Public Hub inventory, observed {observed}">\n{rows}\n</ul>\n'
            f'<p data-szl-inventory="current"><strong>Source-bound snapshot:</strong> {count_line(record)}. '
            f'Observed <time datetime="{observed}">{observed}</time> under <code>{record["scope"]["id"]}</code>. '
            'Native kernel IDs may also appear in the model namespace; these figures do not count unique projects '
            'or trained language models. Private assets, collections and buckets are outside this scope. '
            'This dated observation is not a live count.</p>\n'
            f'<p><a href="{BINDING_URL}">Inventory binding</a> · '
            f'<a href="{source_url(record)}">Exact source inventory</a>. '
            'Membership alone does not establish runtime readiness, model quality, or publication permission. '
            'The governed KEEP list remains <a href="https://github.com/szl-holdings/.github/blob/main/docs/CANONICAL_FLEET.md">'
            'docs/CANONICAL_FLEET.md</a>.</p>')


def replace_block(source: str, content: str) -> str:
    if source.count(START) != 1 or source.count(END) != 1 or source.index(START) >= source.index(END):
        raise InventoryError("exactly one ordered generated inventory block is required")
    before, rest = source.split(START)
    _, after = rest.split(END)
    return before + START + "\n" + content + "\n" + END + after


def refresh(root: Path, record: dict, *, check: bool) -> list[str]:
    validate_binding(record)
    changed = []
    for relative in ("profile/README.md", "huggingface/org-card/README.md", "huggingface/org-card/index.html"):
        path = root / relative
        current = path.read_text(encoding="utf-8")
        rendered = replace_block(current, static(record) if path.suffix == ".html" else markdown(record))
        if current != rendered:
            changed.append(relative)
            if not check:
                path.write_text(rendered, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--source-git-blob")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        binding_path = args.root / "profile/public-inventory.json"
        if args.manifest:
            if args.check or not args.source_revision or not args.source_git_blob:
                raise InventoryError("refresh requires source revision and blob, and cannot use --check")
            record = make_binding(args.manifest.read_bytes(), args.source_revision, args.source_git_blob)
            # Validate all destination markers before writing the source binding.
            refresh(args.root, record, check=True)
            binding_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            if args.source_revision or args.source_git_blob:
                raise InventoryError("source pin inputs require --manifest")
            record = json.loads(binding_path.read_text(encoding="utf-8"))
        changed = refresh(args.root, record, check=args.check)
        if args.check and changed:
            raise InventoryError("generated inventory differs: " + ", ".join(changed))
    except (InventoryError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"profile inventory: {exc}\n")
    print("profile inventory: all four namespace counters and source bindings agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
