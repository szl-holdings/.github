#!/usr/bin/env python3
"""Fail-closed verifier for the sole permanent Space: SZLHOLDINGS/a11oy.

Protected szl-holdings/a11oy@main is the only source authority. This controller
never creates, adopts from, refreshes, republishes, deletes, or changes the
visibility of a clone. Historical clone IDs must remain absent.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from huggingface_hub import HfApi

ORG = "SZLHOLDINGS"
CANONICAL_SPACE = f"{ORG}/a11oy"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
APP_ORIGIN = "https://szlholdings-a11oy.hf.space"
HISTORICAL_CLONE_IDS = tuple(f"{ORG}/a11oy-clone-{i}" for i in range(1, 5))
IMPORTANT_ROUTES = (
    ("/", False),
    ("/api/a11oy/readyz", True),
    ("/api/build-info", True),
    ("/api/a11oy/v1/brain/capabilities", True),
    ("/holographic", False),
)
TERMINAL_STAGES = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HF_BASE = "https://huggingface.co"


@dataclass(frozen=True)
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


def normalize_stage(value: Any) -> str:
    return str(getattr(value, "value", value) or "UNKNOWN").split(".")[-1].upper()


def contains_value(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return any(contains_value(v, expected) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_value(v, expected) for v in value)
    return str(value) == expected


class CanonicalA11oyVerifier:
    def __init__(self, token: str, generation: str, publish: bool) -> None:
        expected = os.environ.get("A11OY_EXPECTED_GITHUB_SHA", "").strip().lower()
        if not SHA_RE.fullmatch(expected):
            raise RuntimeError("A11OY_EXPECTED_GITHUB_SHA must be an exact 40-character SHA")
        self.token = token
        self.generation = generation
        self.publish = publish
        self.expected_github_sha = expected
        self.api = HfApi(token=token)
        self.http = requests.Session()
        self.http.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "szl-a11oy-singleton-verifier/2",
        })
        self.actions: list[Action] = []
        self.counts: dict[str, int] = {}
        self.canonical: dict[str, Any] = {}
        self.routes: list[dict[str, Any]] = []
        self.clone_absence: dict[str, bool] = {}
        self.collection_cleanup: list[str] = []

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>9}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def authenticate(self) -> None:
        who = self.api.whoami()
        match = next((o for o in (who.get("orgs") or [])
                      if str(o.get("name") or o.get("fullname") or "").upper() == ORG), None)
        if not match:
            raise RuntimeError(f"Authenticated identity is not a member of {ORG}")
        role = str(match.get("roleInOrg") or match.get("role") or "").lower()
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"Hugging Face organization role is not write-capable: {role}")
        self.record(ORG, "authenticate", "validated", f"role={role or 'unknown'}")

    def _paginate(self, url: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while url:
            response = self.http.get(url, timeout=45)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "items" in payload:
                payload = payload["items"]
            if not isinstance(payload, list):
                raise TypeError(f"Expected list from {url}")
            out.extend(item for item in payload if isinstance(item, dict))
            url = next((p.split("<", 1)[1].split(">", 1)[0]
                        for p in (response.headers.get("link") or "").split(",")
                        if 'rel="next"' in p), "")
        return out

    def inventory(self) -> None:
        endpoints = {
            "models": f"{HF_BASE}/api/models?author={ORG}&limit=1000&full=true",
            "datasets": f"{HF_BASE}/api/datasets?author={ORG}&limit=1000&full=true",
            "spaces": f"{HF_BASE}/api/spaces?author={ORG}&limit=1000&full=true",
            "kernels": f"{HF_BASE}/api/kernels?author={ORG}&limit=1000",
        }
        for kind, endpoint in endpoints.items():
            try:
                self.counts[kind] = len(self._paginate(endpoint))
                self.record(ORG, f"inventory:{kind}", "validated", f"count={self.counts[kind]}")
            except Exception as exc:  # noqa: BLE001
                self.counts[kind] = -1
                self.record(ORG, f"inventory:{kind}", "warning", repr(exc)[:240])
        try:
            self.counts["collections"] = len(list(self.api.list_collections(owner=ORG, limit=100)))
            self.record(ORG, "inventory:collections", "validated",
                        f"count={self.counts['collections']}")
        except Exception as exc:  # noqa: BLE001
            self.counts["collections"] = -1
            self.record(ORG, "inventory:collections", "warning", repr(exc)[:240])

    def _space_detail(self) -> dict[str, Any]:
        response = self.http.get(f"{HF_BASE}/api/spaces/{CANONICAL_SPACE}", timeout=45)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Canonical Space API did not return an object")
        return payload

    def _canonical_detail(self) -> dict[str, Any]:
        info = self.api.space_info(CANONICAL_SPACE)
        detail = self._space_detail()
        runtime = detail.get("runtime") or {}
        info_runtime = getattr(info, "runtime", None)
        private = detail.get("private")
        if private is None:
            private = getattr(info, "private", None)
        return {
            "repo_id": CANONICAL_SPACE,
            "sha": str(detail.get("sha") or getattr(info, "sha", "") or ""),
            "runtime_sha": str(runtime.get("sha") or runtime.get("revision")
                               or getattr(info_runtime, "sha", "") or ""),
            "stage": normalize_stage(runtime.get("stage") or getattr(info_runtime, "stage", None)),
            "sdk": str(detail.get("sdk") or getattr(info, "sdk", "") or "").lower(),
            "private": private,
            "last_modified": str(detail.get("lastModified") or detail.get("last_modified")
                                 or getattr(info, "last_modified", "") or ""),
        }

    def _public_get(self, path: str) -> requests.Response:
        session = requests.Session()
        session.headers.update({"User-Agent": "szl-a11oy-singleton-verifier/2",
                                "Cache-Control": "no-cache", "Pragma": "no-cache"})
        last = ""
        for attempt in range(1, 6):
            try:
                response = session.get(APP_ORIGIN + path, timeout=45, allow_redirects=True)
                if response.status_code == 200:
                    return response
                last = f"HTTP {response.status_code}"
            except Exception as exc:  # noqa: BLE001
                last = repr(exc)
            if attempt < 5:
                time.sleep(10 * attempt)
        raise RuntimeError(f"Public route failed: {path}: {last}")

    def _probe_routes(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for path, expect_json in IMPORTANT_ROUTES:
            response = self._public_get(path)
            payload: Any = None
            if expect_json:
                try:
                    payload = response.json()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"Expected JSON from {path}: {exc!r}") from exc
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Expected JSON object from {path}")
            if path == "/api/build-info" and not contains_value(payload, self.expected_github_sha):
                raise RuntimeError(f"Build-info lacks protected source {self.expected_github_sha}")
            results.append({"path": path, "status": 200,
                            "content_type": response.headers.get("content-type", "")})
            self.record(CANONICAL_SPACE + path, "canonical-route", "validated")
        return results

    def wait_for_current_canonical(self, timeout_seconds: int = 2400) -> None:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        error = ""
        while time.monotonic() < deadline:
            try:
                if not self.api.repo_exists(CANONICAL_SPACE, repo_type="space"):
                    raise RuntimeError("canonical repository is missing")
                last = self._canonical_detail()
                files = set(self.api.list_repo_files(CANONICAL_SPACE, repo_type="space"))
                if last["private"] is not False:
                    raise RuntimeError("canonical Space is not public")
                if last["sdk"] != "docker":
                    raise RuntimeError(f"canonical SDK={last['sdk']!r}")
                if "Dockerfile" not in files:
                    raise RuntimeError("canonical Space lacks Dockerfile")
                if not SHA_RE.fullmatch(last["sha"]):
                    raise RuntimeError(f"canonical head is not immutable: {last['sha']!r}")
                if last["stage"] in TERMINAL_STAGES:
                    raise RuntimeError(f"canonical terminal stage={last['stage']}")
                if last["stage"] != "RUNNING":
                    raise RuntimeError(f"canonical stage={last['stage']}")
                if last["runtime_sha"] and last["runtime_sha"] != last["sha"]:
                    raise RuntimeError(f"runtime {last['runtime_sha']} != head {last['sha']}")
                self.routes = self._probe_routes()
                last.update(dockerfile_present=True,
                            expected_github_source_sha=self.expected_github_sha)
                self.canonical = last
                self.record(CANONICAL_SPACE, "canonical-singleton", "validated",
                            f"stage=RUNNING; head={last['sha']}; github={self.expected_github_sha}")
                return
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                time.sleep(15)
        raise RuntimeError(f"Canonical A11oy did not verify: last={last}; error={error}")

    def assert_clones_absent(self) -> None:
        present: list[str] = []
        for clone_id in HISTORICAL_CLONE_IDS:
            exists = self.api.repo_exists(clone_id, repo_type="space")
            self.clone_absence[clone_id] = not exists
            self.record(clone_id, "clone-absence", "validated" if not exists else "error",
                        "absent" if not exists else "unexpectedly exists")
            if exists:
                present.append(clone_id)
        if present:
            raise RuntimeError(f"Clone policy violated; use a reviewed GitHub PR: {present}")

    def remove_stale_collection_references(self) -> None:
        clone_ids = set(HISTORICAL_CLONE_IDS)
        for summary in self.api.list_collections(owner=ORG, limit=100):
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in clone_ids:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(target, "collection-remove-stale-clone", "dry-run")
                    continue
                self.api.delete_collection_item(collection_slug=collection.slug,
                                                item_object_id=item.item_object_id,
                                                missing_ok=True)
                self.collection_cleanup.append(target)
                self.record(target, "collection-remove-stale-clone", "deleted")

    def report(self) -> dict[str, Any]:
        summary = {
            "ok": sum(a.status in {"ok", "updated", "validated", "deleted"} for a in self.actions),
            "warning": sum(a.status == "warning" for a in self.actions),
            "error": sum(a.status == "error" for a in self.actions),
            "dry_run": sum(a.status == "dry-run" for a in self.actions),
        }
        return {
            "schema": "szl.hf-a11oy-singleton-report/v1",
            "organization": ORG,
            "generation": self.generation,
            "publish": self.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "expected_github_source_sha": self.expected_github_sha,
            "canonical_flagship_space": self.canonical,
            "historical_clone_ids": list(HISTORICAL_CLONE_IDS),
            "clone_absence": self.clone_absence,
            "critical_route_results": self.routes,
            "removed_stale_collection_references": self.collection_cleanup,
            "inventory_counts": self.counts,
            "singleton_policy": {
                "permanent_a11oy_spaces": [CANONICAL_SPACE],
                "clone_creation_enabled": False,
                "clone_adoption_enabled": False,
                "clone_deletion_enabled": False,
                "source_authority": "szl-holdings/a11oy@protected-main",
                "workflow_recreation_path": "removed",
            },
            "actions": [asdict(a) for a in self.actions],
            "summary": summary,
            "boundaries": [
                "SZLHOLDINGS/a11oy is the only permanent A11oy Hugging Face Space.",
                "Protected GitHub main is authoritative; clone timestamps never select content.",
                "No verifier path creates, adopts from, refreshes, deletes, or changes a clone.",
                "All historical clone IDs must remain absent.",
                "Dockerfile-derived byte parity is enforced in the same workflow.",
                "Critical routes and build identity are probed read-only.",
            ],
        }

    def persist_report(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        Path("reports").mkdir(exist_ok=True)
        Path("reports/hf-estate-upgrade-latest.json").write_bytes(rendered)
        if not self.publish:
            return
        if not self.api.repo_exists(EVIDENCE_DATASET, repo_type="dataset"):
            raise RuntimeError(f"Evidence dataset is missing: {EVIDENCE_DATASET}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for path in ("estate/singleton/latest.json", f"estate/singleton/history/{stamp}.json"):
            self.api.upload_file(repo_id=EVIDENCE_DATASET, repo_type="dataset",
                                 path_or_fileobj=io.BytesIO(rendered), path_in_repo=path,
                                 commit_message=f"chore(estate): verify single A11oy {stamp}",
                                 commit_description="Read-only canonical and clone-absence evidence.")
        self.record(EVIDENCE_DATASET, "publish-singleton-report", "updated")

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.inventory()
        self.wait_for_current_canonical()
        self.assert_clones_absent()
        self.remove_stale_collection_references()
        report = self.report()
        self.persist_report(report)
        report = self.report()
        Path("reports/hf-estate-upgrade-latest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--generation", default=os.environ.get("GITHUB_SHA")
                        or f"manual-{int(time.time())}")
    args = parser.parse_args()
    token = os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_ORG_TOKEN1") \
        or os.environ.get("HF_TOKEN")
    if not token:
        print("FATAL: no supported Hugging Face credential is configured", file=sys.stderr)
        return 2
    try:
        report = CanonicalA11oyVerifier(token, args.generation, args.publish).run()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc!r}", file=sys.stderr)
        return 2
    print(json.dumps(report["summary"], indent=2))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
