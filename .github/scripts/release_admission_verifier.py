#!/usr/bin/env python3
"""Fail-closed release-admission verifier shared by the attestor and the queue.

``attest-and-approve.yml`` runs this before it signs a merge BAP, approves as
the App, or publishes ``attestation/qillqaq``. ``merge-queue-enqueue.yml``
runs it again immediately before ``enqueuePullRequest``. Both must reach the
same evidence fingerprint, and the queue requires the attestor's exact-head
App approval to name that fingerprint.

The verifier binds, for one exact subject:

* the repository, event, pull request, base ref/SHA, head SHA and both trees,
  with the head containing the base (compare ``behind_by == 0`` and
  ``merge_base == base``);
* every required check from its trusted producer workflow and event at the
  exact generation. Check and workflow-run evidence is paginated completely.
  A missing, pending, stale, duplicate, skipped, failed, foreign or
  untrusted-producer check cannot satisfy a requirement, and a different
  successful check never substitutes for another;
* the CP-eBOM receipt from that exact effect run. The verifier downloads the
  run-scoped artifact, checks its published digest, parses the receipt
  strictly and recomputes its canonical decision digest. It also cross-checks
  base/head/merge-base/trees, the changed-path set and the trust-root set
  against GitHub's own compare result. The green job conclusion is never
  treated as an ALLOW bit.

Verdict semantics:

* ``DENY`` always blocks, including when an owner decision exists.
* ``ALLOW`` admits only its exact scope, and only when no admission producer
  or trust root changed.
* ``REVIEW_REQUIRED`` and any admission-producer change hold, unless a
  separately verified owner decision binds the same base, head, head tree,
  raw-diff digest, receipt digest and effect run. The receipt is never
  relabeled ALLOW.

Owner decision record. It is a pull-request conversation comment, unedited,
whose author login is in ``OWNER_DECISION_ACTORS`` and whose account type is
``User``. Its body starts with these lines (free-text rationale may follow
after a blank line)::

    SZL-Admission-Owner-Decision: ACCEPT
    repository: szl-holdings/.github
    pull_request: 123
    base: <40-hex base commit>
    head: <40-hex pull-request head commit>
    head_tree: <40-hex head tree>
    diff_sha256: sha256:<receipt diff_sha256>
    cp_ebom_decision_digest: sha256:<receipt decision_digest>
    cp_ebom_run_id: <effect workflow run id>

``SZL-Admission-Owner-Decision: REVOKE`` with ``repository``, ``pull_request``
and ``head`` withdraws an earlier decision for that head. The PR body is
never consulted, so a self-asserted body string carries no authority.
Limit: this binds a GitHub account identity, not a person. Anyone holding
that account's token can post the record, and automation must never do so.

Network use is limited to read-only GitHub REST GETs with the supplied token.
The artifact download follows exactly one redirect, without the token, to an
allowlisted storage host. No token value is printed or recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any, Callable, Mapping, NamedTuple, Sequence

VERDICT_SCHEMA = "szl.release-admission-verdict/v1"
RECEIPT_SCHEMA = "szl.control-plane-effect-delta/v1"
DECISION_MARKER = "SZL-Admission-Owner-Decision:"
OWNER_DECISION_ACTORS = frozenset({"stephenlutar2-hash"})
TRUSTED_CHECK_APP = ("github-actions", 15368)

GATES_WORKFLOW = ".github/workflows/gates.yml"
GATE_CONTEXTS = (
    "gate/ground-truth",
    "gate/labels",
    "gate/schema",
    "gate/adversarial",
    "gate/verify-all",
    "gate/provenance",
    "gate/a11y-perf",
    "gate/lean",
)
EFFECT_WORKFLOW = ".github/workflows/control-plane-effect-gate.yml"
EFFECT_CONTEXT = "Static control-plane effect boundary"
PROVENANCE_WORKFLOW = ".github/workflows/solo-builder-provenance.yml"
# Each admission event uses only its own provenance job and source event. The
# other event's job is skipped on that head and is never proof.
PROVENANCE_BY_EVENT = {
    "pull_request": ("Exact-head organization provenance", "pull_request_target"),
    "merge_group": ("Exact merge-group provenance", "merge_group"),
}
TRUST_ROOT_PATHS = frozenset({
    ".github/data/control_plane_effect_policy.json",
    ".github/scripts/control_plane_effect_gate.py",
    ".github/scripts/test_control_plane_effect_gate.py",
    ".github/workflows/control-plane-effect-gate.yml",
    "docs/CONTROL_PLANE_EFFECTS.md",
})
# A change to any producer or consumer of admission evidence cannot certify
# itself: its checks may come from the changed code. It needs the owner record.
ADMISSION_PRODUCER_PATHS = TRUST_ROOT_PATHS | frozenset({
    GATES_WORKFLOW,
    PROVENANCE_WORKFLOW,
    ".github/workflows/attest-and-approve.yml",
    ".github/workflows/merge-queue-enqueue.yml",
    ".github/scripts/release_admission_verifier.py",
    ".github/scripts/test_release_admission_verifier.py",
    ".github/scripts/test_attestation_queue_precondition.py",
    ".github/scripts/test_merge_queue_enqueue.py",
    ".github/scripts/test_solo_builder_provenance.py",
    ".github/scripts/run_forge9_gate.py",
})
ADMISSION_PRODUCER_PREFIXES = (".governance/", "provenance/")

EXACT_SHA = re.compile(r"[0-9a-f]{40}")
EXACT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
BASE_REF = re.compile(r"main|release/[A-Za-z0-9._-]+")
API_ROOT = "https://api.github.com"
ARTIFACT_HOST_SUFFIXES = (".githubusercontent.com", ".blob.core.windows.net")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_PAGES = 40
COMPARE_FILE_LIMIT = 300
PENDING_CODES = frozenset({"EVIDENCE_PENDING"})
EXIT_CODES = {"ADMIT": 0, "BLOCK": 2, "HOLD": 3}


class AdmissionError(Exception):
    """Evidence that cannot support admission. ``code`` is stable and public."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class HttpResponse(NamedTuple):
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str]], HttpResponse]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:  # noqa: D401
        return None


def urllib_transport(url: str, headers: Mapping[str, str]) -> HttpResponse:
    """One GET without following redirects (the caller decides every hop)."""
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with opener.open(request, timeout=45) as response:
            return HttpResponse(int(response.status), dict(response.headers.items()),
                                response.read(MAX_JSON_BYTES + 1))
    except urllib.error.HTTPError as exc:
        return HttpResponse(int(exc.code), dict(exc.headers.items()) if exc.headers else {},
                            exc.read(65536) if exc.fp else b"")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AdmissionError("PROVIDER_READ_FAILED", "GitHub read transport failed") from exc


def canonical_bytes(value: Any) -> bytes:
    """The CP-eBOM checker's canonical receipt encoding, byte for byte."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def strict_json(raw: bytes, label: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AdmissionError("EVIDENCE_MALFORMED", f"{label} repeats a JSON key")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        raise AdmissionError("EVIDENCE_MALFORMED", f"{label} has a non-finite number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("EVIDENCE_MALFORMED", f"{label} is not valid JSON") from exc


class GitHubReader:
    """Read-only GitHub REST client with complete, fail-closed pagination."""

    def __init__(self, repository: str, token: str, transport: Transport = urllib_transport,
                 api_root: str = API_ROOT) -> None:
        if not token:
            raise AdmissionError("READ_TOKEN_MISSING", "a read token is required")
        self.repository = repository
        self._token = token
        self._transport = transport
        self._api_root = api_root.rstrip("/")
        self.requests = 0

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "szl-release-admission-verifier/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get(self, route: str) -> Any:
        self.requests += 1
        response = self._transport(f"{self._api_root}/{route}", self._headers())
        if response.status != 200:
            # Never echo a provider body; it can reflect request context.
            raise AdmissionError("PROVIDER_READ_FAILED",
                                 f"GET {route.split('?', 1)[0]} returned HTTP {response.status}")
        if len(response.body) > MAX_JSON_BYTES:
            raise AdmissionError("EVIDENCE_MALFORMED", "GitHub response exceeded the bound")
        return strict_json(response.body, route.split("?", 1)[0])

    def paged(self, route: str, key: str) -> list[dict[str, Any]]:
        """Collect every page of a ``total_count`` collection, or fail closed."""
        separator = "&" if "?" in route else "?"
        items: list[dict[str, Any]] = []
        total: int | None = None
        for page in range(1, MAX_PAGES + 1):
            data = self.get(f"{route}{separator}per_page=100&page={page}")
            if (not isinstance(data, dict) or not isinstance(data.get(key), list)
                    or not isinstance(data.get("total_count"), int)
                    or isinstance(data.get("total_count"), bool)):
                raise AdmissionError("EVIDENCE_MALFORMED", f"{key} page is malformed")
            if total is None:
                total = data["total_count"]
            elif data["total_count"] != total:
                raise AdmissionError("EVIDENCE_AMBIGUOUS", f"{key} changed during pagination")
            if not all(isinstance(item, dict) for item in data[key]):
                raise AdmissionError("EVIDENCE_MALFORMED", f"{key} entries are malformed")
            items.extend(data[key])
            if len(items) >= total or not data[key]:
                break
        if total is None or len(items) != total:
            raise AdmissionError("EVIDENCE_INCOMPLETE", f"{key} pagination is incomplete")
        identities = [item.get("id") for item in items]
        if len(set(map(repr, identities))) != len(identities):
            raise AdmissionError("EVIDENCE_AMBIGUOUS", f"{key} repeats an entry across pages")
        return items

    def paged_array(self, route: str) -> list[dict[str, Any]]:
        """Collect a bare-array collection until a short page, or fail closed."""
        separator = "&" if "?" in route else "?"
        items: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            data = self.get(f"{route}{separator}per_page=100&page={page}")
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                raise AdmissionError("EVIDENCE_MALFORMED", "array page is malformed")
            items.extend(data)
            if len(data) < 100:
                identities = [item.get("id") for item in items]
                if len(set(map(repr, identities))) != len(identities):
                    raise AdmissionError("EVIDENCE_AMBIGUOUS", "array repeats an entry")
                return items
        raise AdmissionError("EVIDENCE_INCOMPLETE", "array pagination exceeded its bound")

    def artifact_zip(self, artifact_id: int) -> bytes:
        route = f"repos/{self.repository}/actions/artifacts/{artifact_id}/zip"
        self.requests += 1
        first = self._transport(f"{self._api_root}/{route}", self._headers())
        if first.status not in (301, 302, 303, 307, 308):
            raise AdmissionError("RECEIPT_UNAVAILABLE",
                                 f"artifact download returned HTTP {first.status}")
        location = next((value for name, value in first.headers.items()
                         if name.lower() == "location"), "")
        parsed = urllib.parse.urlsplit(location)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host.endswith(ARTIFACT_HOST_SUFFIXES):
            raise AdmissionError("RECEIPT_UNAVAILABLE", "artifact redirect host is not allowlisted")
        # The storage URL is pre-signed. The GitHub token is never sent to it.
        self.requests += 1
        second = self._transport(location, {"User-Agent": "szl-release-admission-verifier/1"})
        if second.status != 200:
            raise AdmissionError("RECEIPT_UNAVAILABLE",
                                 f"artifact storage returned HTTP {second.status}")
        if len(second.body) > MAX_ARTIFACT_BYTES:
            raise AdmissionError("RECEIPT_MALFORMED", "artifact exceeded the size bound")
        return second.body


@dataclass(frozen=True)
class Subject:
    repository: str
    event: str
    head_sha: str
    base_ref: str
    base_sha: str
    gate_run_id: int
    pull_request: int
    pr_head_sha: str
    body_sha256: str | None

    def validate(self) -> None:
        if not REPOSITORY.fullmatch(self.repository):
            raise AdmissionError("SUBJECT_INVALID", "repository must be owner/name")
        if self.event not in PROVENANCE_BY_EVENT:
            raise AdmissionError("SUBJECT_INVALID", "event must be pull_request or merge_group")
        for value in (self.head_sha, self.base_sha, self.pr_head_sha):
            if not EXACT_SHA.fullmatch(value or "") or set(value) == {"0"}:
                raise AdmissionError("SUBJECT_INVALID", "commits must be exact nonzero 40-hex SHAs")
        if not BASE_REF.fullmatch(self.base_ref or ""):
            raise AdmissionError("SUBJECT_INVALID", "base ref must be main or release/*")
        if self.gate_run_id < 1 or self.pull_request < 1:
            raise AdmissionError("SUBJECT_INVALID", "gate run and pull request must be positive")
        if self.event == "pull_request":
            if self.pr_head_sha != self.head_sha:
                raise AdmissionError("SUBJECT_INVALID", "pull-request head must be the subject head")
            if not re.fullmatch(r"[0-9a-f]{64}", self.body_sha256 or ""):
                raise AdmissionError("SUBJECT_INVALID", "pull-request body digest is required")
        elif self.base_ref != "main":
            raise AdmissionError("SUBJECT_INVALID", "the merge queue governs main only")


def _commit_tree(reader: GitHubReader, sha: str) -> str:
    commit = reader.get(f"repos/{reader.repository}/git/commits/{sha}")
    tree = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
    if not isinstance(commit, dict) or commit.get("sha") != sha or not EXACT_SHA.fullmatch(str(tree)):
        raise AdmissionError("SUBJECT_MISMATCH", "commit identity or tree is not exact")
    return str(tree)


def _verify_pull_request(reader: GitHubReader, subject: Subject) -> None:
    pull = reader.get(f"repos/{reader.repository}/pulls/{subject.pull_request}")
    if not isinstance(pull, dict):
        raise AdmissionError("EVIDENCE_MALFORMED", "pull request is malformed")
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    expected = {
        "state": "open",
        "draft": False,
        "head_sha": subject.pr_head_sha,
        "head_repository": reader.repository,
        "base_repository": reader.repository,
        "base_ref": subject.base_ref,
    }
    observed = {
        "state": pull.get("state"),
        "draft": pull.get("draft"),
        "head_sha": head.get("sha"),
        "head_repository": (head.get("repo") or {}).get("full_name"),
        "base_repository": (base.get("repo") or {}).get("full_name"),
        "base_ref": base.get("ref"),
    }
    drift = sorted(key for key in expected if observed[key] != expected[key])
    if drift:
        raise AdmissionError("SUBJECT_DRIFT", "pull request changed: " + ",".join(drift))
    if subject.event == "pull_request":
        ref = reader.get(f"repos/{reader.repository}/git/ref/heads/{subject.base_ref}")
        tip = ((ref or {}).get("object") or {}).get("sha") if isinstance(ref, dict) else None
        if tip != subject.base_sha:
            raise AdmissionError("SUBJECT_DRIFT", "base branch tip is not the subject base")


def _changed_paths(reader: GitHubReader, subject: Subject) -> tuple[set[str], str]:
    compare = reader.get(
        f"repos/{reader.repository}/compare/{subject.base_sha}...{subject.head_sha}")
    if not isinstance(compare, dict) or not isinstance(compare.get("files"), list):
        raise AdmissionError("EVIDENCE_MALFORMED", "compare result is malformed")
    merge_base = (compare.get("merge_base_commit") or {}).get("sha")
    if compare.get("behind_by") != 0 or merge_base != subject.base_sha:
        raise AdmissionError("SUBJECT_NOT_UP_TO_DATE", "head does not contain the exact base")
    if compare.get("status") not in {"ahead", "identical"}:
        raise AdmissionError("SUBJECT_NOT_UP_TO_DATE", "head is not ahead of the exact base")
    files = compare["files"]
    if len(files) >= COMPARE_FILE_LIMIT:
        raise AdmissionError("EVIDENCE_INCOMPLETE", "compare may truncate the changed-file set")
    changed: set[str] = set()
    for item in files:
        name = item.get("filename") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            raise AdmissionError("EVIDENCE_MALFORMED", "compare file entry is malformed")
        changed.add(name)
        if item.get("status") == "renamed":
            previous = item.get("previous_filename")
            if not isinstance(previous, str) or not previous:
                raise AdmissionError("EVIDENCE_MALFORMED", "rename lacks its previous path")
            changed.add(previous)
    return changed, str(merge_base)


def _is_trusted_app(check: Mapping[str, Any]) -> bool:
    app = check.get("app") or {}
    return (app.get("slug"), app.get("id")) == TRUSTED_CHECK_APP


def _select_check(
    context: str,
    *,
    workflow: str,
    event: str,
    subject: Subject,
    repository: str,
    checks: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    exact_run_id: int | None = None,
) -> dict[str, Any]:
    by_suite = {run.get("check_suite_id"): run for run in runs}

    def producer(run: Mapping[str, Any] | None) -> bool:
        return bool(run) and (
            run.get("path") == workflow and run.get("event") == event
            and run.get("head_sha") == subject.head_sha
            and (run.get("head_repository") or {}).get("full_name") == repository
        )

    generations = [run for run in runs if producer(run)]
    if not generations:
        raise AdmissionError("EVIDENCE_MISSING", f"{context}: no {event} run of {workflow}")
    newest = max(generations, key=lambda run: int(run.get("id") or 0))
    if exact_run_id is not None and int(newest.get("id") or 0) != exact_run_id:
        raise AdmissionError("EVIDENCE_STALE", f"{context}: a newer generation than the gate run exists")
    generation = exact_run_id if exact_run_id is not None else int(newest["id"])
    ignored = {"untrusted_producer": 0, "foreign": 0, "stale": 0}
    current: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for check in checks:
        if check.get("name") != context:
            continue
        if not _is_trusted_app(check):
            ignored["untrusted_producer"] += 1
            continue
        run = by_suite.get((check.get("check_suite") or {}).get("id"))
        if check.get("head_sha") != subject.head_sha or not producer(run):
            ignored["foreign"] += 1
            continue
        if int(run.get("id") or 0) != generation:
            ignored["stale"] += 1
            continue
        current.append((run, check))
    if not current:
        if newest.get("status") != "completed":
            raise AdmissionError("EVIDENCE_PENDING", f"{context}: producer run is not complete")
        raise AdmissionError("EVIDENCE_MISSING", f"{context}: no trusted current-generation check")
    if len(current) != 1:
        raise AdmissionError("EVIDENCE_AMBIGUOUS", f"{context}: duplicate current-generation checks")
    run, check = current[0]
    if check.get("status") != "completed":
        raise AdmissionError("EVIDENCE_PENDING", f"{context}: check is not complete")
    if check.get("conclusion") != "success":
        raise AdmissionError("EVIDENCE_NOT_SUCCESS",
                             f"{context}: conclusion is {check.get('conclusion')}")
    return {
        "context": context,
        "check_run_id": int(check["id"]),
        "workflow": workflow,
        "event": event,
        "run_id": int(run["id"]),
        "run_attempt": int(run.get("run_attempt") or 0),
        "conclusion": "success",
        "ignored": ignored,
    }


def _receipt_from_artifact(reader: GitHubReader, run_id: int, subject: Subject) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = reader.paged(f"repos/{reader.repository}/actions/runs/{run_id}/artifacts", "artifacts")
    name = f"control-plane-effect-{run_id}"
    matches = [item for item in artifacts if item.get("name") == name]
    if len(matches) != 1:
        raise AdmissionError("RECEIPT_UNAVAILABLE" if not matches else "EVIDENCE_AMBIGUOUS",
                             f"expected one {name} artifact")
    artifact = matches[0]
    workflow_run = artifact.get("workflow_run") or {}
    digest = str(artifact.get("digest") or "")
    if (artifact.get("expired") is not False or workflow_run.get("id") != run_id
            or workflow_run.get("head_sha") != subject.head_sha or not EXACT_DIGEST.fullmatch(digest)):
        raise AdmissionError("RECEIPT_UNAVAILABLE", "effect artifact is expired, foreign or undigested")
    archive = reader.artifact_zip(int(artifact["id"]))
    if sha256_bytes(archive) != digest:
        raise AdmissionError("RECEIPT_TAMPERED", "artifact bytes do not match the published digest")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            for member in members:
                parts = member.filename.split("/")
                if member.filename.startswith("/") or ".." in parts or "\\" in member.filename:
                    raise AdmissionError("RECEIPT_MALFORMED", "artifact has an unsafe member path")
            reports = [member for member in members if member.filename == "report.json"]
            if len(reports) != 1 or reports[0].file_size > MAX_RECEIPT_BYTES:
                raise AdmissionError("RECEIPT_MALFORMED", "artifact needs exactly one bounded report.json")
            raw = bundle.read(reports[0])
    except zipfile.BadZipFile as exc:
        raise AdmissionError("RECEIPT_MALFORMED", "artifact is not a zip archive") from exc
    receipt = strict_json(raw, "CP-eBOM receipt")
    if not isinstance(receipt, dict):
        raise AdmissionError("RECEIPT_MALFORMED", "receipt root must be an object")
    return receipt, {"artifact_id": int(artifact["id"]), "artifact_digest": digest}


def _verify_receipt(
    receipt: Mapping[str, Any],
    *,
    subject: Subject,
    head_tree: str,
    base_tree: str,
    changed: set[str],
    merge_base: str,
) -> dict[str, Any]:
    claimed = receipt.get("decision_digest")
    body = {key: value for key, value in receipt.items() if key != "decision_digest"}
    try:
        recomputed = sha256_bytes(canonical_bytes(body))
    except (TypeError, ValueError) as exc:
        raise AdmissionError("RECEIPT_MALFORMED", "receipt is not canonical JSON") from exc
    if not EXACT_DIGEST.fullmatch(str(claimed)) or recomputed != claimed:
        raise AdmissionError("RECEIPT_TAMPERED", "receipt decision digest does not recompute")
    verdict = receipt.get("verdict")
    claims = {
        "ALLOW": {"VERIFIED_STATIC_EFFECT_BOUNDARY", "NO_DECLARED_CONTROL_PLANE_EFFECT_CHANGE"},
        "REVIEW_REQUIRED": {"TRUST_ROOT_CHANGED_REVIEW_REQUIRED"},
        "DENY": {"DENIED_STATIC_EFFECT_BOUNDARY"},
    }
    if receipt.get("schema") != RECEIPT_SCHEMA or verdict not in claims:
        raise AdmissionError("RECEIPT_MALFORMED", "receipt schema or verdict is unsupported")
    if receipt.get("claim") not in claims[verdict]:
        raise AdmissionError("RECEIPT_INCONSISTENT", "receipt claim does not match its verdict")
    if verdict == "DENY":
        # Identity checks are moot: DENY blocks whatever it is bound to.
        return {"verdict": "DENY", "decision_digest": claimed,
                "reason_codes": list(receipt.get("reason_codes") or [])}
    for flag in ("provider_calls_performed", "secret_values_requested", "secret_values_recorded"):
        if receipt.get(flag) is not False:
            raise AdmissionError("RECEIPT_INCONSISTENT", f"receipt {flag} is not false")
    identity = {
        "base_revision": subject.base_sha,
        "head_revision": subject.head_sha,
        "merge_base": merge_base,
        "head_tree": head_tree,
        "base_tree": base_tree,
    }
    drift = sorted(key for key, value in identity.items() if receipt.get(key) != value)
    if drift:
        raise AdmissionError("RECEIPT_SCOPE_MISMATCH", "receipt is for another subject: " + ",".join(drift))
    paths = receipt.get("changed_paths")
    if not isinstance(paths, list) or set(paths) != changed or len(paths) != len(set(paths)):
        raise AdmissionError("RECEIPT_INCONSISTENT", "receipt changed paths differ from GitHub compare")
    trust_root = sorted(changed & TRUST_ROOT_PATHS)
    if receipt.get("trust_root_changes") != trust_root:
        raise AdmissionError("RECEIPT_INCONSISTENT", "receipt trust-root set differs from compare")
    reasons = receipt.get("reason_codes")
    checker = receipt.get("checker") or {}
    policy = receipt.get("policy") or {}
    if not isinstance(reasons, list):
        raise AdmissionError("RECEIPT_MALFORMED", "receipt reason codes are malformed")
    if verdict == "ALLOW" and (reasons or trust_root):
        raise AdmissionError("RECEIPT_INCONSISTENT", "ALLOW cannot carry reasons or trust-root changes")
    if verdict == "REVIEW_REQUIRED" and (
            not trust_root or "TRUST_ROOT_CHANGED_REVIEW_REQUIRED" not in reasons):
        raise AdmissionError("RECEIPT_INCONSISTENT", "REVIEW_REQUIRED must be a trust-root transition")
    if not trust_root:
        # Unchanged trust root: the base checker and base policy produced it.
        if (not EXACT_DIGEST.fullmatch(str(checker.get("base_sha256")))
                or checker.get("base_sha256") != checker.get("head_sha256")
                or policy.get("authority_revision") != subject.base_sha):
            raise AdmissionError("RECEIPT_INCONSISTENT", "receipt checker/policy authority is not the base")
    elif policy.get("authority_revision") != subject.head_sha:
        raise AdmissionError("RECEIPT_INCONSISTENT", "trust-root receipt must use the head policy")
    if not EXACT_DIGEST.fullmatch(str(receipt.get("diff_sha256"))):
        raise AdmissionError("RECEIPT_MALFORMED", "receipt diff digest is malformed")
    return {
        "verdict": verdict,
        "decision_digest": claimed,
        "diff_sha256": receipt["diff_sha256"],
        "reason_codes": sorted(reasons),
        "trust_root_changes": trust_root,
    }


def _decision_block(body: Any) -> dict[str, str] | None:
    if not isinstance(body, str):
        return None
    lines = body.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].startswith(DECISION_MARKER):
        return None
    action = lines[0][len(DECISION_MARKER):].strip()
    fields: dict[str, str] = {"action": action}
    for line in lines[1:]:
        if not line.strip():
            break
        key, separator, value = line.partition(":")
        key = key.strip()
        if not separator or not re.fullmatch(r"[a-z_0-9]+", key) or key in fields:
            return {"action": "MALFORMED"}
        fields[key] = value.strip()
    return fields


def _owner_decision(
    reader: GitHubReader,
    subject: Subject,
    *,
    head_tree: str,
    receipt: Mapping[str, Any],
    effect_run: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str], dict[str, int]]:
    comments = reader.paged_array(
        f"repos/{reader.repository}/issues/{subject.pull_request}/comments")
    ignored = {"untrusted_author": 0, "edited": 0, "malformed": 0, "other_head": 0}
    latest: tuple[int, dict[str, str], Mapping[str, Any]] | None = None
    for comment in comments:
        block = _decision_block(comment.get("body"))
        if block is None:
            continue
        user = comment.get("user") or {}
        if user.get("login") not in OWNER_DECISION_ACTORS or user.get("type") != "User":
            ignored["untrusted_author"] += 1
            continue
        if not comment.get("created_at") or comment.get("created_at") != comment.get("updated_at"):
            ignored["edited"] += 1
            continue
        if block.get("action") not in {"ACCEPT", "REVOKE"}:
            ignored["malformed"] += 1
            continue
        if block.get("head") != subject.pr_head_sha:
            ignored["other_head"] += 1
            continue
        identity = int(comment.get("id") or 0)
        if latest is None or identity > latest[0]:
            latest = (identity, block, comment)
    if latest is None:
        return None, ["OWNER_DECISION_MISSING"], ignored
    identity, block, comment = latest
    record = {"comment_id": identity, "author": (comment.get("user") or {}).get("login"),
              "action": block["action"], "created_at": comment.get("created_at")}
    if block["action"] == "REVOKE":
        return record, ["OWNER_DECISION_REVOKED"], ignored
    expected = {
        "repository": subject.repository,
        "pull_request": str(subject.pull_request),
        "base": subject.base_sha,
        "head": subject.pr_head_sha,
        "head_tree": head_tree,
        "diff_sha256": str(receipt.get("diff_sha256")),
    }
    if subject.event == "pull_request":
        # The PR-head receipt itself is what the owner accepted.
        expected["cp_ebom_decision_digest"] = str(receipt.get("decision_digest"))
        expected["cp_ebom_run_id"] = str(effect_run["run_id"])
        if str(comment.get("created_at")) < str(effect_run.get("created_at") or ""):
            return record, ["OWNER_DECISION_PREDATES_EVIDENCE"], ignored
    # A merge-group receipt has new commit identities but must carry the same
    # base, tree and raw diff the owner accepted on the pull-request head.
    mismatched = sorted(key for key, value in expected.items() if block.get(key) != value)
    required = {"repository", "pull_request", "base", "head", "head_tree", "diff_sha256",
                "cp_ebom_decision_digest", "cp_ebom_run_id"}
    missing = sorted(required - set(block))
    if missing or mismatched:
        return record, ["OWNER_DECISION_MISMATCH:" + ",".join(missing + mismatched)], ignored
    return record, [], ignored


def verify(subject: Subject, reader: GitHubReader, *, phase: str) -> dict[str, Any]:
    """Return an ADMIT/HOLD/BLOCK verdict. Raises AdmissionError only for BLOCK."""
    subject.validate()
    if phase not in {"attest", "enqueue"}:
        raise AdmissionError("SUBJECT_INVALID", "phase must be attest or enqueue")
    repository = subject.repository
    head_tree = _commit_tree(reader, subject.head_sha)
    base_tree = _commit_tree(reader, subject.base_sha)
    _verify_pull_request(reader, subject)
    changed, merge_base = _changed_paths(reader, subject)
    checks = reader.paged(
        f"repos/{repository}/commits/{subject.head_sha}/check-runs?filter=latest", "check_runs")
    runs = reader.paged(f"repos/{repository}/actions/runs?head_sha={subject.head_sha}", "workflow_runs")

    gate_event = subject.event
    bindings = [
        _select_check(context, workflow=GATES_WORKFLOW, event=gate_event, subject=subject,
                      repository=repository, checks=checks, runs=runs,
                      exact_run_id=subject.gate_run_id)
        for context in GATE_CONTEXTS
    ]
    provenance_context, provenance_event = PROVENANCE_BY_EVENT[subject.event]
    bindings.append(_select_check(provenance_context, workflow=PROVENANCE_WORKFLOW,
                                  event=provenance_event, subject=subject,
                                  repository=repository, checks=checks, runs=runs))
    effect = _select_check(EFFECT_CONTEXT, workflow=EFFECT_WORKFLOW, event=subject.event,
                           subject=subject, repository=repository, checks=checks, runs=runs)
    bindings.append(effect)
    effect_run = next(run for run in runs if int(run.get("id") or 0) == effect["run_id"])
    receipt, artifact = _receipt_from_artifact(reader, effect["run_id"], subject)
    summary = _verify_receipt(receipt, subject=subject, head_tree=head_tree, base_tree=base_tree,
                              changed=changed, merge_base=merge_base)
    producer_changes = sorted(path for path in changed if path in ADMISSION_PRODUCER_PATHS
                              or path.startswith(ADMISSION_PRODUCER_PREFIXES))
    evidence: dict[str, Any] = {
        "head_tree": head_tree,
        "base_tree": base_tree,
        "merge_base": merge_base,
        "changed_path_count": len(changed),
        "admission_producer_changes": producer_changes,
        "checks": bindings,
        "effect": {
            "run_id": effect["run_id"],
            "run_attempt": effect["run_attempt"],
            **artifact,
            **summary,
        },
        "owner_decision": None,
        "ignored_owner_decision_comments": None,
    }
    reasons: list[str] = []
    basis: str
    if summary["verdict"] == "DENY":
        decision, basis, reasons = "BLOCK", "CP_EBOM_DENY", ["CP_EBOM_DENY"]
    elif summary["verdict"] == "ALLOW" and not producer_changes:
        decision, basis = "ADMIT", "CP_EBOM_ALLOW_EXACT_SCOPE"
    else:
        record, problems, ignored = _owner_decision(
            reader, subject, head_tree=head_tree, receipt=receipt,
            effect_run={"run_id": effect["run_id"], "created_at": effect_run.get("created_at")})
        evidence["owner_decision"] = record
        evidence["ignored_owner_decision_comments"] = ignored
        if problems:
            decision, basis, reasons = "HOLD", "OWNER_DECISION_REQUIRED", problems
        else:
            decision = "ADMIT"
            basis = ("REVIEW_REQUIRED_OWNER_ACCEPTED" if summary["verdict"] == "REVIEW_REQUIRED"
                     else "PRODUCER_CHANGE_OWNER_ACCEPTED")
    fingerprint_source = {
        "schema": VERDICT_SCHEMA,
        "repository": repository,
        "event": subject.event,
        "pull_request": subject.pull_request,
        "head_sha": subject.head_sha,
        "pr_head_sha": subject.pr_head_sha,
        "head_tree": head_tree,
        "base_ref": subject.base_ref,
        "base_sha": subject.base_sha,
        "body_sha256": subject.body_sha256,
        "gate_run_id": subject.gate_run_id,
        "checks": [{key: item[key] for key in ("context", "check_run_id", "run_id", "run_attempt")}
                   for item in bindings],
        "effect": {key: evidence["effect"][key] for key in
                   ("run_id", "run_attempt", "artifact_id", "artifact_digest", "decision_digest", "verdict")},
        "owner_decision_comment_id": (evidence["owner_decision"] or {}).get("comment_id"),
        "decision": decision,
        "basis": basis,
    }
    return {
        "schema": VERDICT_SCHEMA,
        "phase": phase,
        "subject": {
            "repository": repository,
            "event": subject.event,
            "pull_request": subject.pull_request,
            "head_sha": subject.head_sha,
            "pr_head_sha": subject.pr_head_sha,
            "base_ref": subject.base_ref,
            "base_sha": subject.base_sha,
            "body_sha256": subject.body_sha256,
            "gate_run_id": subject.gate_run_id,
        },
        "decision": decision,
        "basis": basis,
        "reasons": reasons,
        "receipt_verdict": summary["verdict"],
        "evidence": evidence,
        "evidence_fingerprint": sha256_bytes(canonical_bytes(fingerprint_source)),
        "github_reads": reader.requests,
        "network": "read-only GitHub REST GET",
        "provider_writes_performed": False,
        "token_value_recorded": False,
    }


def blocked(subject: Subject | None, phase: str, exc: AdmissionError, reads: int) -> dict[str, Any]:
    return {
        "schema": VERDICT_SCHEMA,
        "phase": phase,
        "subject": None if subject is None else {
            "repository": subject.repository, "event": subject.event,
            "pull_request": subject.pull_request, "head_sha": subject.head_sha,
            "base_sha": subject.base_sha, "gate_run_id": subject.gate_run_id,
        },
        "decision": "BLOCK",
        "basis": exc.code,
        "reasons": [f"{exc.code}: {exc.detail}"],
        "receipt_verdict": None,
        "evidence": None,
        "evidence_fingerprint": None,
        "github_reads": reads,
        "network": "read-only GitHub REST GET",
        "provider_writes_performed": False,
        "token_value_recorded": False,
    }


def verify_with_wait(
    subject: Subject,
    reader: GitHubReader,
    *,
    phase: str,
    wait_seconds: int,
    poll_seconds: int,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Retry only while evidence is still running; every other failure is final."""
    deadline = clock() + max(0, wait_seconds)
    while True:
        try:
            return verify(subject, reader, phase=phase)
        except AdmissionError as exc:
            if exc.code not in PENDING_CODES or clock() + poll_seconds > deadline:
                return blocked(subject, phase, exc, reader.requests)
        sleep(poll_seconds)


def write_json(path: str, value: Mapping[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "wb") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None, *, transport: Transport = urllib_transport,
         environ: Mapping[str, str] = os.environ) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--gate-run-id", required=True)
    parser.add_argument("--pull-request", required=True)
    parser.add_argument("--pr-head-sha", required=True)
    parser.add_argument("--body-sha256", default=None)
    parser.add_argument("--phase", required=True, choices=("attest", "enqueue"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--token-env", default="GH_TOKEN")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    subject: Subject | None = None
    reads = 0
    try:
        try:
            gate_run_id = int(args.gate_run_id)
            pull_request = int(args.pull_request)
        except ValueError as exc:
            raise AdmissionError("SUBJECT_INVALID", "run and PR identifiers must be integers") from exc
        subject = Subject(
            repository=args.repository, event=args.event, head_sha=args.head_sha.lower(),
            base_ref=args.base_ref, base_sha=args.base_sha.lower(), gate_run_id=gate_run_id,
            pull_request=pull_request, pr_head_sha=args.pr_head_sha.lower(),
            body_sha256=(args.body_sha256 or None),
        )
        subject.validate()
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", args.token_env):
            raise AdmissionError("SUBJECT_INVALID", "token environment name is invalid")
        reader = GitHubReader(subject.repository, environ.get(args.token_env, ""), transport)
        result = verify_with_wait(subject, reader, phase=args.phase,
                                  wait_seconds=args.wait_seconds, poll_seconds=max(1, args.poll_seconds))
    except AdmissionError as exc:
        result = blocked(subject, args.phase, exc, reads)
    except Exception as exc:  # fail closed on any verifier defect
        result = blocked(subject, args.phase,
                         AdmissionError("VERIFIER_INTERNAL_ERROR", type(exc).__name__), reads)
    write_json(args.output, result)
    print(f"release admission {result['decision']} ({result['basis']}); "
          f"fingerprint {result['evidence_fingerprint']}; reasons {result['reasons']}")
    return EXIT_CODES[result["decision"]]


if __name__ == "__main__":
    raise SystemExit(main())
