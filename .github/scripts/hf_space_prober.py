#!/usr/bin/env python3
"""Hugging Face organization prober: Space runtime, visibility and card governance.

Reads the live Hub API for one organization and records, per asset:
  - visibility (private/public)
  - Space runtime stage (RUNNING / BUILDING / RUNTIME_ERROR / PAUSED / SLEEPING / ...)
  - declared license
  - presence of a governance stamp carrying a literal model-ID backlink

Every row carries a doctrine label: MEASURED when the API answered, UNAVAILABLE
when it refused, UNKNOWN when the field was never probed. Nothing is inferred.

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
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HUB = "https://huggingface.co"
UA = "szl-hf-space-prober/1.0"
RUNNING = "RUNNING"
STAMP_HINTS = ("governance", "governed", "measured truth", "provenance")
BACKLINK = re.compile(r"(?:huggingface\.co/(?:spaces/|datasets/)?[\w.-]+/[\w.-]+)|(?:github\.com/szl-holdings/[\w.-]+)", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hub_get(path: str, token: str | None, raw: bool = False):
    url = path if path.startswith("http") else HUB + path
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
                return (body if raw else json.loads(body or "null")), resp.status
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(4 * (attempt + 1))
                continue
            return None, exc.code
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(3)
                continue
            return None, 0
    return None, 0


def list_repos(kind: str, org: str, token: str | None) -> tuple[list, int]:
    q = urllib.parse.urlencode({"author": org, "full": "true", "limit": 1000})
    body, status = hub_get(f"/api/{kind}?{q}", token)
    return (body if isinstance(body, list) else []), status


def card_text(kind: str, repo_id: str, token: str | None) -> tuple[str, str]:
    seg = {"spaces": "spaces/", "datasets": "datasets/", "models": ""}[kind]
    body, status = hub_get(f"/{seg}{repo_id}/raw/main/README.md", token, raw=True)
    if status == 200 and isinstance(body, str):
        return body, "MEASURED"
    return "", "UNAVAILABLE" if status in (401, 403) else "UNKNOWN"


def probe(kind: str, org: str, token: str | None, check_cards: bool) -> tuple[list, dict]:
    repos, status = list_repos(kind, org, token)
    rows: list[dict] = []
    if status != 200:
        return rows, {"listing_status": status, "label": "UNAVAILABLE"}

    for r in repos:
        repo_id = r.get("id") or f"{org}/{r.get('modelId', '?')}"
        row = {
            "repo_id": repo_id,
            "kind": kind,
            "private": bool(r.get("private")),
            "gated": r.get("gated", False),
            "likes": r.get("likes", 0),
            "last_modified": r.get("lastModified"),
            "license": ((r.get("cardData") or {}).get("license")
                        or next((t.split(":", 1)[1] for t in (r.get("tags") or [])
                                 if t.startswith("license:")), None)),
            "label": "MEASURED",
        }
        if kind == "spaces":
            runtime = r.get("runtime") or {}
            row["stage"] = runtime.get("stage") or "UNKNOWN"
            row["hardware"] = (runtime.get("hardware") or {}).get("current")
            row["sdk"] = r.get("sdk")
            row["running"] = row["stage"] == RUNNING
            row["public_and_running"] = (not row["private"]) and row["running"]
        if check_cards:
            text, label = card_text(kind, repo_id, token)
            low = text.lower()
            row["card_label"] = label
            row["card_bytes"] = len(text)
            row["has_stamp"] = bool(text) and any(h in low for h in STAMP_HINTS)
            row["has_backlink"] = bool(BACKLINK.search(text))
        rows.append(row)

    spaces = [x for x in rows if x["kind"] == "spaces"]
    summary = {
        f"{kind}_total": len(rows),
        f"{kind}_public": sum(1 for x in rows if not x["private"]),
        f"{kind}_private": sum(1 for x in rows if x["private"]),
    }
    if kind == "spaces":
        summary["public_not_running"] = sum(
            1 for x in spaces if not x["private"] and not x.get("running"))
        summary["stages"] = {}
        for x in spaces:
            summary["stages"][x.get("stage", "UNKNOWN")] = summary["stages"].get(x.get("stage", "UNKNOWN"), 0) + 1
    if check_cards:
        summary[f"{kind}_missing_stamp"] = sum(
            1 for x in rows if x.get("card_label") == "MEASURED" and not x.get("has_stamp"))
        summary[f"{kind}_missing_backlink"] = sum(
            1 for x in rows if x.get("card_label") == "MEASURED" and not x.get("has_backlink"))
        summary[f"{kind}_card_unreadable"] = sum(
            1 for x in rows if x.get("card_label") != "MEASURED")
    summary[f"{kind}_missing_license"] = sum(1 for x in rows if not x.get("license"))
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default=os.environ.get("HF_ORG", "SZLHOLDINGS"))
    ap.add_argument("--kinds", default="spaces,models,datasets")
    ap.add_argument("--out-json", default="reports/governance/hf-spaces.json")
    ap.add_argument("--out-md", default="reports/governance/hf-spaces.md")
    ap.add_argument("--skip-cards", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = next((os.environ[k] for k in
                  ("HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_TOKEN", "HF_WRITE_TOKEN")
                  if os.environ.get(k)), None)
    if not token:
        print("WARN: no HF token; private assets will report UNAVAILABLE", file=sys.stderr)

    all_rows, summary = [], {}
    for kind in [k.strip() for k in args.kinds.split(",") if k.strip()]:
        rows, s = probe(kind, args.org, token, not args.skip_cards)
        all_rows.extend(rows)
        summary.update(s)

    summary["missing_stamp"] = sum(v for k, v in summary.items() if k.endswith("_missing_stamp"))
    summary["missing_license"] = sum(v for k, v in summary.items() if k.endswith("_missing_license"))
    summary["public_not_running"] = summary.get("public_not_running", 0)
    summary["token_present"] = bool(token)

    payload = {
        "schema": "szl.governance.hf_probe/v1",
        "generated_at": utc_now(),
        "hf_org": args.org,
        "summary": summary,
        "assets": all_rows,
        "receipt_state": "UNSIGNED_HONEST",
    }

    md = [f"# Hugging Face estate probe \u2014 `{args.org}`", "",
          f"- generated_at: `{utc_now()}`", ""]
    for k in sorted(summary):
        md.append(f"- {k}: {summary[k]}")
    offenders = [x for x in all_rows
                 if (x["kind"] == "spaces" and not x["private"] and not x.get("running"))
                 or (x.get("card_label") == "MEASURED" and not x.get("has_stamp"))]
    if offenders:
        md += ["", "## Assets needing action", "",
               "| repo | kind | private | stage | stamp | license |",
               "| --- | --- | --- | --- | --- | --- |"]
        for x in offenders[:200]:
            md.append(f"| `{x['repo_id']}` | {x['kind']} | {x['private']} | "
                      f"{x.get('stage', '-')} | {x.get('has_stamp', '-')} | {x.get('license') or '-'} |")

    for path, blob in ((args.out_json, json.dumps(payload, indent=2, sort_keys=True) + "\n"),
                       (args.out_md, "\n".join(md) + "\n")):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(blob)

    print(f"hf probe: {summary.get('spaces_total', 0)} spaces, "
          f"{summary.get('public_not_running', 0)} public not running, "
          f"{summary.get('missing_stamp', 0)} missing stamp")
    if args.dry_run:
        return 0
    return 1 if (summary.get("public_not_running", 0) or summary.get("missing_stamp", 0)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
