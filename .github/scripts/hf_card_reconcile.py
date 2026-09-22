#!/usr/bin/env python3
"""Reconcile SZLHOLDINGS Hub card metadata against a declarative JSON expectation.

The JSON in .github/config/hf_card_expectations.json is the owner-authored
statement of expected card state. This tool never invents a fact: it only
applies values that are written in that file, and it only touches keys the file
names. Absent keys are left byte-identical.

Front matter is edited surgically. A card body is replaced only when the
expectation names a body_file AND --allow-body-replace is passed, so a routine
metadata reconcile can never silently rewrite prose.

Default mode is plan-only. --apply performs Hub commits.

stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HUB = "https://huggingface.co"
UA = "szl-hf-card-reconcile/1.0"
SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")
MEASURED, UNAVAILABLE = "MEASURED", "UNAVAILABLE"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hub_request(method: str, path: str, token: str | None, body: bytes | None = None,
                content_type: str | None = None):
    url = path if path.startswith("http") else HUB + path
    headers = {"User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8", "replace"), resp.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(4 * (attempt + 1))
                continue
            return detail, exc.code
        except urllib.error.URLError as exc:
            if attempt < 2:
                time.sleep(3)
                continue
            return str(exc), 0
    return "", 0


def split_front_matter(text: str) -> tuple[str, str]:
    """Return (front_matter_block, remainder). Block excludes the --- fences."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    fm = text[4:end] if text[3] == "\n" else text[3:end]
    rest = text[end + 4:]
    return fm, rest.lstrip("\n")


def fm_keys(fm: str) -> dict:
    out = {}
    for line in fm.splitlines():
        if line.startswith((" ", "\t", "-")):
            continue
        m = SCALAR.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def set_scalar(fm: str, key: str, value: str) -> tuple[str, bool]:
    """Insert or update one top-level scalar, preserving every other line."""
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        m = SCALAR.match(line)
        if m and m.group(1) == key:
            if m.group(2).strip().strip("'\"") == value:
                return fm, False
            lines[i] = f"{key}: {value}"
            return "\n".join(lines), True
    # Insert only after a top-level scalar that actually carries a value and is
    # not the header of an indented block. Inserting after a bare "tags:" would
    # split that key from its list items and corrupt the card.
    insert_at = len(lines)
    for i, line in enumerate(lines):
        m = SCALAR.match(line)
        if not m or line.startswith((" ", "\t", "-")):
            continue
        if not m.group(2).strip():
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt.startswith((" ", "\t", "-")):
            continue
        insert_at = i + 1
    lines.insert(insert_at, f"{key}: {value}")
    return "\n".join(lines), True


def stamp_block(asset: dict, defaults: dict) -> str:
    repo_id = asset["repo_id"]
    source = asset.get("source_repo")
    heading = defaults.get("stamp_heading", "## Governance")
    lines = [heading, "",
             f"- Hub repository: `{repo_id}`"]
    if source:
        lines.append(f"- Source of truth: [github.com/{source}](https://github.com/{source})")
    lines += ["- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE",
              "- Receipts remain UNSIGNED_HONEST until the DSSE lane signs", ""]
    return "\n".join(lines)


def has_stamp(body: str, asset: dict) -> bool:
    low = body.lower()
    if "governance" not in low and "governed" not in low:
        return False
    return asset["repo_id"].lower() in low or (
        asset.get("source_repo", "\0").lower() in low)


def plan_asset(asset: dict, defaults: dict, token: str | None, bodies_dir: str,
               allow_body: bool) -> dict:
    repo_id = asset["repo_id"]
    kind = asset.get("kind", "spaces")
    seg = {"spaces": "spaces/", "datasets": "datasets/", "models": ""}[kind]
    text, status = hub_request("GET", f"/{seg}{repo_id}/raw/main/README.md", token)
    row = {"repo_id": repo_id, "kind": kind, "label": MEASURED, "changes": [],
           "reason": asset.get("reason", "")}
    if status != 200:
        row.update({"label": UNAVAILABLE, "detail": f"card read HTTP {status}"})
        return row

    fm, body = split_front_matter(text)
    if not fm:
        row.update({"label": UNAVAILABLE, "detail": "no YAML front matter found"})
        return row

    original_bytes = len(text)
    existing = fm_keys(fm)

    for key in ("license", "title", "short_description"):
        want = asset.get(key) if key != "license" else asset.get("license", defaults.get("license"))
        if not want:
            continue
        if key != "license" and existing.get(key):
            continue
        quoted = f'"{want}"' if key == "short_description" else want
        fm, changed = set_scalar(fm, key, quoted)
        if changed:
            row["changes"].append(f"front_matter.{key}={want}")

    body_file = asset.get("body_file")
    if body_file and allow_body:
        path = os.path.join(bodies_dir, body_file)
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        row["changes"].append(f"body<={body_file}")

    if asset.get("require_stamp", defaults.get("require_stamp", True)) and not has_stamp(body, asset):
        body = body.rstrip("\n") + "\n\n" + stamp_block(asset, defaults)
        row["changes"].append("body+=governance_stamp")

    new_text = "---\n" + fm.strip("\n") + "\n---\n\n" + body.lstrip("\n")
    row["new_text"] = new_text
    row["bytes_before"] = original_bytes
    row["bytes_after"] = len(new_text)
    return row


def apply_asset(row: dict, token: str, message: str) -> dict:
    kind = row["kind"]
    seg = {"spaces": "spaces", "datasets": "datasets", "models": "models"}[kind]
    header = {"key": "header", "value": {"summary": message}}
    filerec = {"key": "file", "value": {"path": "README.md", "encoding": "utf-8",
                                        "content": row["new_text"]}}
    ndjson = (json.dumps(header) + "\n" + json.dumps(filerec) + "\n").encode("utf-8")
    detail, status = hub_request(
        "POST", f"/api/{seg}/{row['repo_id']}/commit/main", token, ndjson,
        "application/x-ndjson")
    row["apply_status"] = status
    row["applied"] = status in (200, 201)
    if not row["applied"]:
        row["apply_detail"] = detail[:300]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=".github/config/hf_card_expectations.json")
    ap.add_argument("--bodies-dir", default=".github/config/hf_cards")
    ap.add_argument("--out-json", default="reports/governance/hf-card-reconcile.json")
    ap.add_argument("--only", default="", help="comma-separated repo_id filter")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--allow-body-replace", action="store_true")
    ap.add_argument("--message", default="chore(card): reconcile governed card metadata")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        cfg = json.load(fh)
    defaults = cfg.get("defaults", {})
    assets = cfg.get("assets", [])
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        assets = [a for a in assets if a["repo_id"] in wanted]

    token = next((os.environ[k] for k in
                  ("HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_TOKEN", "HF_WRITE_TOKEN")
                  if os.environ.get(k)), None)
    if args.apply and not token:
        print("FATAL: --apply requires an HF token", file=sys.stderr)
        return 2

    rows = []
    for asset in assets:
        row = plan_asset(asset, defaults, token, args.bodies_dir, args.allow_body_replace)
        if args.apply and row["label"] == MEASURED and row["changes"]:
            apply_asset(row, token, args.message)
        rows.append(row)

    payload = {
        "schema": "szl.governance.hf_card_reconcile/v1",
        "generated_at": utc_now(),
        "mode": "apply" if args.apply else "plan",
        "body_replace_allowed": bool(args.allow_body_replace),
        "assets": [{k: v for k, v in r.items() if k != "new_text"} for r in rows],
        "receipt_state": "UNSIGNED_HONEST",
    }
    os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    for r in rows:
        print(f"{r['repo_id']}: {r['label']} changes={r['changes']} "
              f"applied={r.get('applied', 'plan-only')}")

    unavailable = [r for r in rows if r["label"] == UNAVAILABLE]
    failed = [r for r in rows if args.apply and r["changes"] and not r.get("applied")]
    return 1 if (unavailable or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
