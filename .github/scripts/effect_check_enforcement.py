#!/usr/bin/env python3
"""Bind the required effect check to the release-admission owner decision.

ALLOW still passes from the analyzer exit alone. DENY still fails.
REVIEW_REQUIRED stays the receipt verdict and passes only when
release_admission_verifier accepts an unedited owner decision for the
pull-request head. A missing, edited, stale-head, or wrong-owner comment
fails. A merge-group run uses that same pull-request head and still requires
the group's base, tree, and raw diff to be the ones the owner accepted.

This module does not change a ruleset, post a comment, or rewrite a
historical pull request.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_EXPECTED = {0: "ALLOW", 2: "DENY", 3: "REVIEW_REQUIRED"}
_SHA = re.compile(r"[0-9a-f]{40}")
_QUEUE_REF = re.compile(
    r"(?:refs/heads/)?gh-readonly-queue/main/pr-([1-9][0-9]*)-[0-9a-f]{40}"
)
_VERIFIER_PATH = Path(__file__).with_name("release_admission_verifier.py")


def check_decision(exit_code: int, verdict: object) -> str:
    """Return PASS, FAIL, or DISAGREE. REVIEW_REQUIRED is not an analyzer pass."""
    expected = _EXPECTED.get(exit_code)
    if expected is None or verdict != expected:
        return "DISAGREE"
    if verdict == "ALLOW":
        return "PASS"
    return "FAIL"


def _verifier():
    spec = importlib.util.spec_from_file_location(
        "release_admission_verifier", _VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("release admission verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _CommentReader:
    def __init__(self, comments: list[dict], repository: str) -> None:
        self._comments = comments
        self.repository = repository

    def paged_array(self, route: str) -> list[dict]:
        if not isinstance(self._comments, list):
            raise SystemExit("owner-decision comments are malformed")
        return self._comments


def queue_pull_request(ref: str) -> int | None:
    """Return the pull-request number named by a main merge-queue ref."""
    match = _QUEUE_REF.fullmatch(ref or "")
    if match is None:
        return None
    return int(match.group(1))


def bind_owner_decision(
    receipt: dict,
    comments: list[dict],
    *,
    repository: str,
    pull_request: int,
    run_id: str,
    run_created_at: str,
    event: str = "pull_request",
    pr_head_sha: str = "",
) -> tuple[str, list[str]]:
    """Return ADMIT or HOLD and the verifier reason list. The receipt is unchanged."""
    verifier = _verifier()
    head = str(receipt.get("head_revision") or "")
    base = str(receipt.get("base_revision") or "")
    if event == "merge_group":
        if not pr_head_sha:
            return "HOLD", ["OWNER_DECISION_MISSING"]
        decided_head = pr_head_sha
        body_sha256 = None
    elif event == "pull_request":
        decided_head = head
        body_sha256 = "0" * 64
    else:
        return "HOLD", ["SUBJECT_INVALID"]
    subject = verifier.Subject(
        repository=repository,
        event=event,
        head_sha=head,
        base_ref="main",
        base_sha=base,
        gate_run_id=1,
        pull_request=pull_request,
        pr_head_sha=decided_head,
        body_sha256=body_sha256,
    )
    try:
        subject.validate()
    except verifier.AdmissionError as exc:
        return "HOLD", [str(exc.code)]
    _record, problems, _ignored = verifier._owner_decision(
        _CommentReader(comments, repository),
        subject,
        head_tree=str(receipt.get("head_tree") or ""),
        receipt=receipt,
        effect_run={"run_id": run_id, "created_at": run_created_at},
    )
    if problems:
        return "HOLD", problems
    return "ADMIT", []


def enforce(
    exit_code: int,
    receipt_path: Path,
    status_path: Path,
    *,
    comments_path: Path | None = None,
    repository: str = "",
    pull_request: int = 0,
    run_id: str = "",
    run_created_at: str = "",
    event: str = "pull_request",
    pr_head_sha: str = "",
) -> int:
    if not receipt_path.is_file():
        status_path.write_text(
            "verdict=MISSING\nclaim=MISSING\ndecision=FAIL\nowner=NOT_READ\nowner_reasons=RECEIPT_MISSING\n",
            encoding="utf-8",
        )
        raise SystemExit("the analyzer did not emit a receipt")
    try:
        receipt = json.loads(receipt_path.read_text("utf-8"))
    except json.JSONDecodeError:
        receipt = None
    if not isinstance(receipt, dict):
        status_path.write_text(
            "verdict=MALFORMED\nclaim=MALFORMED\ndecision=FAIL\nowner=NOT_READ\nowner_reasons=RECEIPT_MALFORMED\n",
            encoding="utf-8",
        )
        raise SystemExit("the analyzer receipt is malformed")
    verdict = receipt.get("verdict")
    decision = check_decision(exit_code, verdict)
    owner = "NOT_REQUIRED"
    reasons: list[str] = []
    if decision == "DISAGREE":
        outcome = "DISAGREE"
    elif verdict == "ALLOW":
        outcome = "PASS"
    elif verdict == "REVIEW_REQUIRED":
        comments: list[dict] = []
        if comments_path is not None and comments_path.is_file():
            loaded = json.loads(comments_path.read_text("utf-8"))
            if not isinstance(loaded, list):
                raise SystemExit("owner-decision comments are malformed")
            comments = loaded
        owner, reasons = bind_owner_decision(
            receipt,
            comments,
            repository=repository,
            pull_request=pull_request,
            run_id=run_id,
            run_created_at=run_created_at,
            event=event,
            pr_head_sha=pr_head_sha,
        )
        outcome = "PASS" if owner == "ADMIT" else "FAIL"
    else:
        outcome = "FAIL"
    reason_text = ",".join(reasons) if reasons else "none"
    status_path.write_text(
        "\n".join((
            f"verdict={verdict}",
            f"claim={receipt.get('claim', 'MISSING')}",
            f"decision={outcome}",
            f"owner={owner}",
            f"owner_reasons={reason_text}",
            "",
        )),
        encoding="utf-8",
    )
    if outcome == "DISAGREE":
        raise SystemExit("analyzer exit and receipt verdict do not agree")
    if outcome != "PASS":
        raise SystemExit(exit_code)
    return 0


def _write_subject(path: Path, event: str, pull_request: int, pr_head_sha: str) -> None:
    path.write_text(json.dumps({
        "event": event,
        "pull_request": pull_request,
        "pr_head_sha": pr_head_sha,
    }), encoding="utf-8")


def _github_get(url: str, token: str) -> tuple[object, str]:
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "szl-effect-check",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            link = response.headers.get("Link", "")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub API returned HTTP {exc.code}") from None
    return payload, link


def _next_page(link: str) -> str:
    for part in link.split(","):
        if 'rel="next"' not in part:
            continue
        raw = part.split(";", 1)[0].strip()
        if len(raw) < 2 or raw[0] != "<" or raw[-1] != ">":
            raise SystemExit("comment page link is malformed")
        target = raw[1:-1]
        if not target.startswith("https://api.github.com/"):
            raise SystemExit("comment page link is not the GitHub API")
        return target
    return ""


def _pull_head(repository: str, number: int, token: str) -> str:
    payload, _link = _github_get(
        f"https://api.github.com/repos/{repository}/pulls/{number}", token)
    if not isinstance(payload, dict):
        raise SystemExit("pull request is malformed")
    head = payload.get("head") if isinstance(payload.get("head"), dict) else {}
    repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
    sha = str(head.get("sha") or "")
    if repo.get("full_name") != repository or _SHA.fullmatch(sha) is None:
        raise SystemExit("pull request head is not this repository")
    if payload.get("state") != "open" or payload.get("draft") is not False:
        raise SystemExit("pull request is not an open non-draft")
    return sha


def fetch_comments(path: Path, created_path: Path, subject_path: Path) -> int:
    """Write comments, the run timestamp, and the decision subject. Never prints the token."""
    event = os.environ.get("GITHUB_EVENT_NAME") or ""
    if event == "merge_group":
        number = queue_pull_request(os.environ.get("GITHUB_REF") or "")
        if number is None:
            raise SystemExit("merge-group ref is not a main queue pull request")
        number_text = str(number)
    elif event == "pull_request":
        number_text = os.environ.get("PR_NUMBER") or "0"
        if number_text in {"", "0"}:
            path.write_text("[]", encoding="utf-8")
            created_path.write_text("", encoding="utf-8")
            _write_subject(subject_path, event, 0, "")
            return 0
    else:
        path.write_text("[]", encoding="utf-8")
        created_path.write_text("", encoding="utf-8")
        _write_subject(subject_path, event or "unknown", 0, "")
        return 0
    token = os.environ.get("GH_TOKEN") or ""
    if not token:
        raise SystemExit("pull-request comment read has no token")
    repository = os.environ.get("GITHUB_REPOSITORY") or ""
    run_id = os.environ.get("GITHUB_RUN_ID") or ""
    if not repository or not run_id:
        raise SystemExit("pull-request comment read has no repository or run")
    url = f"https://api.github.com/repos/{repository}/issues/{number_text}/comments?per_page=100"
    items: list = []
    for _page in range(10):
        page, link = _github_get(url, token)
        if not isinstance(page, list) or not all(isinstance(item, dict) for item in page):
            raise SystemExit("comment page is malformed")
        items.extend(page)
        next_url = _next_page(link)
        if not next_url or len(page) < 100:
            break
        url = next_url
    else:
        raise SystemExit("comment pagination exceeded its bound")
    created_payload, _link = _github_get(
        f"https://api.github.com/repos/{repository}/actions/runs/{run_id}", token)
    if not isinstance(created_payload, dict):
        raise SystemExit("workflow run is malformed")
    created = str(created_payload.get("created_at") or "")
    pr_head = _pull_head(repository, int(number_text), token) if event == "merge_group" else ""
    path.write_text(json.dumps(items), encoding="utf-8")
    created_path.write_text(created, encoding="utf-8")
    _write_subject(subject_path, event, int(number_text), pr_head)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-comments", action="store_true")
    parser.add_argument("--comments", type=Path)
    parser.add_argument("--run-created-path", type=Path)
    parser.add_argument("--subject", type=Path)
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--repository", default="")
    parser.add_argument("--pull-request", type=int, default=0)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-created-at", default="")
    parser.add_argument("--event", default="pull_request")
    parser.add_argument("--pr-head", default="")
    args = parser.parse_args(argv)
    try:
        if args.fetch_comments:
            if args.comments is None or args.run_created_path is None or args.subject is None:
                raise SystemExit(
                    "comment fetch needs --comments, --run-created-path, and --subject")
            return fetch_comments(args.comments, args.run_created_path, args.subject)
        if args.exit_code is None or args.receipt is None or args.status is None:
            raise SystemExit("enforce needs --exit-code, --receipt, and --status")
        event = args.event
        pull_request = args.pull_request
        pr_head = args.pr_head
        if args.subject is not None:
            if not args.subject.is_file():
                raise SystemExit("owner-decision subject is missing")
            loaded = json.loads(args.subject.read_text("utf-8"))
            if not isinstance(loaded, dict):
                raise SystemExit("owner-decision subject is malformed")
            if "event" in loaded:
                event = str(loaded["event"])
            if "pull_request" in loaded:
                pull_request = int(loaded["pull_request"])
            if loaded.get("pr_head_sha"):
                pr_head = str(loaded["pr_head_sha"])
        return enforce(
            args.exit_code,
            args.receipt,
            args.status,
            comments_path=args.comments,
            repository=args.repository,
            pull_request=pull_request,
            run_id=args.run_id,
            run_created_at=args.run_created_at,
            event=event,
            pr_head_sha=pr_head,
        )
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            raise
        print(code, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    raise SystemExit(main())
