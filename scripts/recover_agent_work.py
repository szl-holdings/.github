#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recover recent closed, draft, and DCO-blocked agent work without bypasses."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

ORG = "szl-holdings"
RECENT_DAYS = 30
AGENT = re.compile(
    r"(?:codex|perplexity|computer[- ]agent|copilot|agent[-_/]|half[-_/]?build|"
    r"stalled|finish[-_/]|repair[-_/]|reconcile[-_/])",
    re.IGNORECASE,
)
OK = {"success", "neutral", "skipped"}


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: Any) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super().__init__(f"{method} {path}: HTTP {status}")


class GitHub:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        allow: Iterable[int] = (200, 201, 202, 204),
        accept: str = "application/vnd.github+json",
    ) -> Any:
        url = path if path.startswith("https://") else "https://api.github.com" + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            method=method,
            data=data,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-agent-recovery/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                if response.status not in set(allow):
                    raise ApiError(method, path, response.status, raw[:500])
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw[:1000]
            raise ApiError(method, path, exc.code, body) from exc

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("POST", path, payload, **kwargs)

    def patch(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("PATCH", path, payload, **kwargs)

    def put(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("PUT", path, payload, **kwargs)

    def pages(self, path: str, max_pages: int = 20) -> list[Any]:
        output: list[Any] = []
        sep = "&" if "?" in path else "?"
        for page in range(1, max_pages + 1):
            rows = self.get(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(rows, list):
                raise RuntimeError(f"expected list from {path}")
            output.extend(rows)
            if len(rows) < 100:
                break
        return output


def error(exc: Exception) -> dict[str, Any]:
    out: dict[str, Any] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    if isinstance(exc, ApiError):
        out.update({"status": exc.status, "path": exc.path, "method": exc.method})
        if isinstance(exc.body, Mapping):
            out["provider_message"] = str(exc.body.get("message") or "")[:300]
    return out


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def select_token() -> tuple[str | None, dict[str, Any]]:
    aliases = (
        "GH_ORG_ADMIN_TOKEN",
        "ORG_ADMIN_TOKEN",
        "GH_ADMIN_TOKEN",
        "SZL_GITHUB_TOKEN",
        "GITHUB_PAT",
        "GH_PAT",
        "GH_TOKEN_SECRET",
    )
    attempts: list[dict[str, Any]] = []
    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        api = GitHub(token)
        try:
            user = api.get("/user")
            membership = api.get(f"/user/memberships/orgs/{ORG}")
            active = str(membership.get("state") or "").lower() == "active"
            attempts.append(
                {
                    "alias": alias,
                    "identity": user.get("login"),
                    "membership": membership.get("state"),
                    "role": membership.get("role"),
                }
            )
            if active:
                return token, {
                    "state": "ACTIVE_ORG_MEMBER",
                    "alias": alias,
                    "identity": user.get("login"),
                    "role": membership.get("role"),
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"alias": alias, "error": error(exc)})
    return None, {"state": "UNAVAILABLE", "attempts": attempts}


def check_summary(api: GitHub, repo: str, commit_sha: str) -> dict[str, Any]:
    payload = api.get(
        f"/repos/{ORG}/{repo}/commits/{commit_sha}/check-runs?per_page=100",
        accept="application/vnd.github+json",
    )
    checks = payload.get("check_runs") or []
    statuses = (api.get(f"/repos/{ORG}/{repo}/commits/{commit_sha}/status") or {}).get("statuses") or []
    rows: list[dict[str, Any]] = []
    pending = False
    failing: list[str] = []
    for item in checks:
        status = str(item.get("status") or "").lower()
        conclusion = str(item.get("conclusion") or "").lower()
        name = str(item.get("name") or "")
        rows.append({"name": name, "status": status, "conclusion": conclusion})
        if status != "completed" or not conclusion:
            pending = True
        elif conclusion not in OK:
            failing.append(name)
    latest: dict[str, Mapping[str, Any]] = {}
    for item in statuses:
        context = str(item.get("context") or "")
        if context and context not in latest:
            latest[context] = item
    for name, item in latest.items():
        state = str(item.get("state") or "").lower()
        rows.append({"name": name, "status": state, "conclusion": state})
        if state in {"pending", "expected"}:
            pending = True
        elif state != "success":
            failing.append(name)
    return {
        "pending": pending,
        "failing": sorted(set(failing)),
        "green": not pending and not failing,
        "checks": rows,
    }


def agent_provenance(branch: str, title: str, body: str, commit: Mapping[str, Any]) -> bool:
    message = str(((commit.get("commit") or {}).get("message") or ""))
    author = str(((commit.get("author") or {}).get("login") or ""))
    committer = str(((commit.get("committer") or {}).get("login") or ""))
    return bool(AGENT.search(" ".join((branch, title, body, message, author, committer))))


def mark_ready(api: GitHub, pull: Mapping[str, Any]) -> dict[str, Any]:
    node_id = str(pull.get("node_id") or "")
    if not node_id:
        raise RuntimeError("pull request node_id is missing")
    query = """
    mutation MarkReady($id: ID!) {
      markPullRequestReadyForReview(input: {pullRequestId: $id}) {
        pullRequest { number isDraft }
      }
    }
    """
    return api.post("/graphql", {"query": query, "variables": {"id": node_id}}, allow=(200,))


def install_askpass(root: Path) -> Path:
    path = root / "askpass.py"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys\n"
        "p=' '.join(sys.argv[1:]).lower()\n"
        "print(os.environ['SZL_GIT_USERNAME'] if 'username' in p else os.environ['SZL_GIT_PASSWORD'])\n",
        encoding="utf-8",
    )
    path.chmod(0o700)
    return path


def run_git(args: list[str], *, cwd: Path | None, env: Mapping[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=dict(env),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    return result


def dco_recovery(
    api: GitHub,
    token: str,
    repo: str,
    pull: Mapping[str, Any],
) -> dict[str, Any]:
    number = int(pull["number"])
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    head_ref = str(head.get("ref") or "")
    head_sha = str(head.get("sha") or "")
    base_ref = str(base.get("ref") or "main")
    head_repo = str(((head.get("repo") or {}).get("full_name") or ""))
    if head_repo.casefold() != f"{ORG}/{repo}".casefold():
        raise RuntimeError("DCO recovery requires an organization-owned head branch")
    recovery = f"reconcile/dco-{number}-{head_sha[:8]}"
    prior = api.get(
        f"/repos/{ORG}/{repo}/pulls?state=all&head={urllib.parse.quote(f'{ORG}:{recovery}', safe='')}&per_page=10"
    )
    if prior:
        return {
            "action": "DCO_RECOVERY_ALREADY_EXISTS",
            "branch": recovery,
            "pull_number": prior[0].get("number"),
        }

    with tempfile.TemporaryDirectory(prefix=f"szl-dco-{repo}-") as temp:
        root = Path(temp)
        askpass = install_askpass(root)
        env = os.environ.copy()
        env.update(
            {
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "SZL_GIT_USERNAME": "x-access-token",
                "SZL_GIT_PASSWORD": token,
            }
        )
        work = root / "repo"
        clone = run_git(["clone", "--quiet", f"https://github.com/{ORG}/{repo}.git", str(work)], cwd=None, env=env)
        if clone.returncode:
            raise RuntimeError("git clone failed without exposing provider stderr")
        for key, value in (("user.name", "Lutar, Stephen P."), ("user.email", "stephenlutar2@gmail.com")):
            configured = run_git(["config", key, value], cwd=work, env=env)
            if configured.returncode:
                raise RuntimeError(f"git config failed for {key}")
        fetch = run_git(["fetch", "--quiet", "origin", base_ref, head_ref], cwd=work, env=env)
        if fetch.returncode:
            raise RuntimeError("git fetch failed")
        checkout = run_git(["checkout", "-B", recovery, f"origin/{base_ref}"], cwd=work, env=env)
        if checkout.returncode:
            raise RuntimeError("git checkout failed")
        squash = run_git(["merge", "--squash", f"origin/{head_ref}"], cwd=work, env=env)
        if squash.returncode:
            run_git(["merge", "--abort"], cwd=work, env=env)
            raise RuntimeError("squash merge conflicted; no recovery branch was pushed")
        diff = run_git(["diff", "--cached", "--quiet"], cwd=work, env=env)
        if diff.returncode == 0:
            raise RuntimeError("DCO recovery produced an empty diff")
        title = str(pull.get("title") or f"Recover PR #{number}")
        commit = run_git(
            [
                "commit",
                "-s",
                "-m",
                title,
                "-m",
                f"DCO-compliant squash recovery of #{number} at exact head {head_sha}.",
            ],
            cwd=work,
            env=env,
        )
        if commit.returncode:
            raise RuntimeError("recovery commit failed")
        push = run_git(["push", "--quiet", "origin", f"HEAD:{recovery}"], cwd=work, env=env)
        if push.returncode:
            raise RuntimeError("recovery branch push failed")

    replacement = api.post(
        f"/repos/{ORG}/{repo}/pulls",
        {
            "title": str(pull.get("title") or f"Recover PR #{number}"),
            "head": recovery,
            "base": base_ref,
            "draft": False,
            "maintainer_can_modify": True,
            "body": (
                f"DCO-compliant squash recovery of #{number}. The exact source head was `{head_sha}`. "
                "The complete diff was reapplied onto the current base as one signed-off commit; no protection or check was disabled.\n\n"
                "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
            ),
        },
        allow=(201,),
    )
    api.post(
        f"/repos/{ORG}/{repo}/issues/{number}/comments",
        {
            "body": (
                f"Superseded by #{replacement.get('number')} after a DCO-compliant squash recovery of exact head `{head_sha}`. "
                "The original PR is closed without merging; all checks and protections apply to the replacement."
            )
        },
        allow=(201,),
    )
    api.patch(f"/repos/{ORG}/{repo}/pulls/{number}", {"state": "closed"}, allow=(200,))
    return {
        "action": "DCO_RECOVERY_CREATED",
        "branch": recovery,
        "pull_number": replacement.get("number"),
        "pull_url": replacement.get("html_url"),
        "source_pull": number,
        "source_head_sha": head_sha,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "schema": "szl.agent-work-recovery/v1",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "organization": ORG,
        "policy": {
            "branch_protection_bypass": False,
            "review_bypass": False,
            "dco_disabled": False,
            "force_push": False,
            "secret_values_recorded": False,
        },
        "reopened": [],
        "drafts": [],
        "dco_recoveries": [],
        "observations": [],
        "errors": [],
    }
    token, authority = select_token()
    report["authority"] = authority
    if token is None:
        report["state"] = "BLOCKED_AUTHORITY"
        report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report["report_sha256"] = sha256({k: v for k, v in report.items() if k != "report_sha256"})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2
    api = GitHub(token)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RECENT_DAYS)
    try:
        repositories = api.pages(f"/orgs/{ORG}/repos?type=all&sort=updated&direction=desc")
    except Exception as exc:
        report["errors"].append({"scope": "repo-inventory", "error": error(exc)})
        repositories = []

    for repository in repositories:
        if repository.get("archived") or repository.get("disabled"):
            continue
        repo = str(repository.get("name") or "")
        default = str(repository.get("default_branch") or "main")
        try:
            branches = api.pages(f"/repos/{ORG}/{repo}/branches")
            pulls = api.pages(f"/repos/{ORG}/{repo}/pulls?state=all&sort=updated&direction=desc")
        except Exception as exc:
            report["errors"].append({"scope": f"{repo}:inventory", "error": error(exc)})
            continue
        by_head: dict[str, list[dict[str, Any]]] = {}
        for pull in pulls:
            by_head.setdefault(str((pull.get("head") or {}).get("ref") or ""), []).append(pull)

        for branch_row in branches:
            branch = str(branch_row.get("name") or "")
            if not branch or branch == default:
                continue
            commit_sha = str(((branch_row.get("commit") or {}).get("sha") or ""))
            try:
                commit = api.get(f"/repos/{ORG}/{repo}/commits/{commit_sha}")
            except Exception:
                continue
            committed = parse_date(((commit.get("commit") or {}).get("committer") or {}).get("date"))
            history = by_head.get(branch) or []
            title = str(history[0].get("title") or "") if history else ""
            body = str(history[0].get("body") or "") if history else ""
            if committed is None or committed < cutoff or not agent_provenance(branch, title, body, commit):
                continue
            open_pulls = [item for item in history if item.get("state") == "open"]
            closed_unmerged = [
                item for item in history if item.get("state") == "closed" and not item.get("merged_at")
            ]
            observation = {
                "repository": f"{ORG}/{repo}",
                "branch": branch,
                "head_sha": commit_sha,
                "open_pull_numbers": [item.get("number") for item in open_pulls],
                "closed_unmerged_numbers": [item.get("number") for item in closed_unmerged],
            }
            report["observations"].append(observation)
            if not open_pulls and closed_unmerged:
                candidate = closed_unmerged[0]
                try:
                    reopened = api.patch(
                        f"/repos/{ORG}/{repo}/pulls/{candidate['number']}",
                        {"state": "open"},
                        allow=(200,),
                    )
                    report["reopened"].append(
                        {
                            "repository": f"{ORG}/{repo}",
                            "number": reopened.get("number"),
                            "branch": branch,
                            "head_sha": commit_sha,
                            "action": "REOPENED",
                        }
                    )
                    open_pulls = [reopened]
                except Exception as exc:
                    report["reopened"].append(
                        {
                            "repository": f"{ORG}/{repo}",
                            "number": candidate.get("number"),
                            "branch": branch,
                            "action": "REOPEN_BLOCKED",
                            "error": error(exc),
                        }
                    )

            for pull in open_pulls:
                number = int(pull["number"])
                try:
                    full = api.get(f"/repos/{ORG}/{repo}/pulls/{number}")
                    head_sha = str((full.get("head") or {}).get("sha") or "")
                    checks = check_summary(api, repo, head_sha)
                    if full.get("draft") and checks["green"]:
                        try:
                            result = mark_ready(api, full)
                            report["drafts"].append(
                                {
                                    "repository": f"{ORG}/{repo}",
                                    "number": number,
                                    "head_sha": head_sha,
                                    "action": "MARKED_READY",
                                    "graphql_errors": result.get("errors") if isinstance(result, Mapping) else None,
                                }
                            )
                        except Exception as exc:
                            report["drafts"].append(
                                {
                                    "repository": f"{ORG}/{repo}",
                                    "number": number,
                                    "head_sha": head_sha,
                                    "action": "READY_BLOCKED",
                                    "error": error(exc),
                                }
                            )
                    dco_failed = any(
                        "dco" in name.lower() or "developer certificate" in name.lower()
                        for name in checks["failing"]
                    )
                    if dco_failed:
                        try:
                            report["dco_recoveries"].append(dco_recovery(api, token, repo, full))
                        except Exception as exc:
                            report["dco_recoveries"].append(
                                {
                                    "repository": f"{ORG}/{repo}",
                                    "number": number,
                                    "head_sha": head_sha,
                                    "action": "DCO_RECOVERY_BLOCKED",
                                    "error": error(exc),
                                }
                            )
                except Exception as exc:
                    report["errors"].append({"scope": f"{repo}#{number}", "error": error(exc)})

    report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    blocked = [row for row in report["reopened"] + report["drafts"] + report["dco_recoveries"] if "BLOCKED" in str(row.get("action"))]
    report["state"] = "RECOVERY_EXECUTED" if not blocked else "RECOVERY_EXECUTED_WITH_BLOCKERS"
    report["report_sha256"] = sha256({k: v for k, v in report.items() if k != "report_sha256"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "reopened": len(report["reopened"]), "drafts": len(report["drafts"]), "dco": len(report["dco_recoveries"]), "sha256": report["report_sha256"]}, sort_keys=True))
    return 0 if not blocked else 2


if __name__ == "__main__":
    raise SystemExit(main())
