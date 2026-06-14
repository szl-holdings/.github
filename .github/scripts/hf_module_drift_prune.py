#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
"""
Auto-pruner for the GitHub<->HF-Space module-drift allowlists (org-level).

The drift guard (hf_module_drift_check.py) records KNOWN, pre-existing
GitHub<->HF divergences in each repo's ``.github/hf-module-drift-allow.json``
under ``accepted_divergences`` so the gate lands green while a human reconciles
the file. But drift is VOLATILE: a sibling rebuild can make the two sides
byte-identical again days later, and nobody goes back to delete the now-stale
entry. The allowlist then over-counts and HIDES whether a real divergence still
remains -- the exact thing the guard exists to surface.

This janitor mirrors the org-wide drift sweep: it iterates the same
``hf_space_registry.json`` and, for every ``accepted_divergences`` entry whose
two sides are NOW byte-identical (GitHub git-blob sha == live HF Space tree
oid), opens (or updates) a signed pull request that removes JUST those entries.

Safety properties (all deliberate):
  * It NEVER removes a still-divergent entry -- only entries proven identical.
  * It NEVER touches ``ignore_paths`` / ``ignore_extensions``.
  * It is FAIL-CLOSED: if it cannot reach EITHER side for a repo (GitHub tree or
    HF tree unreachable), it removes nothing for that repo and says so. No
    silent removal on a transient outage.
  * An HF-LFS-stored file is not cheaply comparable, so it is kept (cannot be
    proven identical -> fail closed).
  * The PR commit is created via the GitHub GraphQL ``createCommitOnBranch``
    mutation, so the commit is signed/verified by GitHub.

stdlib only (no huggingface_hub / requests). The drift detection reuses the
tree-fetching helpers in hf_module_drift_check.py so the two stay in lockstep.

Run modes:
  * (default)   report-only: print what WOULD be pruned; never writes. Exit 0.
  * --apply     open/update a signed PR per repo with reconciled entries.

Exit status:
  0  normal run (including "nothing to prune" and fail-closed skips).
  1  --apply was requested but a PR could not be created/updated, OR an
     unexpected error occurred. (A side being unreachable is a warning + skip,
     not a hard failure -- that is the fail-closed contract.)
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request

GH_API = "https://api.github.com"
UA = {"User-Agent": "hf-module-drift-prune/1.0"}

DEFAULT_ALLOW_PATH = ".github/hf-module-drift-allow.json"
DEFAULT_BRANCH = "automation/hf-drift-prune-allowlist"
# DCO sign-off identity -- matches the identity the org drift sweep commits as.
SIGNOFF_NAME = "Stephen P. Lutar Jr."
SIGNOFF_EMAIL = "stephenlutar2@gmail.com"


# --------------------------------------------------------------------------- #
# Load the checker module (shares the GitHub/HF tree helpers) by file path so
# this works regardless of the current working directory.
# --------------------------------------------------------------------------- #
def _load_checker():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "hf_module_drift_check.py")
    spec = importlib.util.spec_from_file_location("hf_module_drift_check", path)
    assert spec and spec.loader, f"cannot load checker at {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()


# --------------------------------------------------------------------------- #
# Pure logic (no network) -- the testable core.
# --------------------------------------------------------------------------- #
def classify_entries(accepted, gh_files, hf_files):
    """Decide, for each ``accepted_divergences`` path, whether it is now
    byte-identical (safe to remove) or still divergent / uncomparable (keep).

    ``accepted``  -- dict {path: reason} from the repo allowlist.
    ``gh_files``  -- dict {path: git-blob-sha} from the GitHub side.
    ``hf_files``  -- dict {path: {"oid":..., "lfs_oid":..., "size":...}}.

    Returns (remove, keep) where ``remove`` is a sorted list of paths now
    identical and ``keep`` is an ordered dict {path: reason-string}.
    """
    remove = []
    keep = {}
    for path in accepted:
        gh_sha = gh_files.get(path)
        hf = hf_files.get(path)
        if gh_sha is None and hf is None:
            keep[path] = "absent on BOTH sides (not proven identical)"
            continue
        if gh_sha is None:
            keep[path] = "present on HF but MISSING on GitHub (still divergent)"
            continue
        if hf is None:
            keep[path] = "present on GitHub but MISSING on HF (still divergent)"
            continue
        if hf.get("lfs_oid"):
            keep[path] = "stored as LFS on HF; not cheaply comparable (kept)"
            continue
        if gh_sha == hf.get("oid"):
            remove.append(path)
        else:
            keep[path] = "content still differs (github sha != hf oid)"
    return sorted(remove), keep


def prune_allowlist(allow, to_remove):
    """Return a NEW allowlist dict with ``to_remove`` paths dropped from
    ``accepted_divergences``. Every other key (``_comment``, ``ignore_paths``,
    ``ignore_extensions``, and any non-reconciled accepted entries) is left
    byte-for-byte intact, preserving order."""
    out = {}
    drop = set(to_remove)
    for k, v in allow.items():
        if k == "accepted_divergences" and isinstance(v, dict):
            out[k] = {p: r for p, r in v.items() if p not in drop}
        else:
            out[k] = v
    return out


def serialize_allow(allow):
    """Canonical on-disk form for an allowlist file (matches the existing
    2-space-indented files, with a trailing newline)."""
    return json.dumps(allow, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Per-repo planning (network via injectable fetchers, so tests stub them).
# --------------------------------------------------------------------------- #
def _default_fetch_gh(gh_repo, ref):
    return checker.github_tree_remote(gh_repo, ref)


def _default_fetch_hf(hf_repo, ref):
    return checker.hf_tree(hf_repo, ref)


def plan_repo(gh_repo, hf_repo, ref, allow, *,
              fetch_gh=_default_fetch_gh, fetch_hf=_default_fetch_hf):
    """Compute the prune plan for one GitHub<->HF pair. FAIL-CLOSED: if either
    side cannot be reached, returns skipped=<reason> and removes nothing.

    Returns a dict:
      { github, hf, ref, accepted_count, removed:[...], kept:{...},
        skipped:<reason or None>, new_allow:<dict or None> }
    """
    res = {
        "github": gh_repo, "hf": hf_repo, "ref": ref,
        "accepted_count": 0, "removed": [], "kept": {},
        "skipped": None, "new_allow": None,
    }
    accepted = (allow or {}).get("accepted_divergences", {}) or {}
    res["accepted_count"] = len(accepted)
    if not accepted:
        return res  # nothing recorded -> nothing to prune

    # Fail-closed: BOTH sides must be reachable before we dare remove anything.
    try:
        gh_files = fetch_gh(gh_repo, ref)
    except Exception as e:  # noqa: BLE001 -- any failure to reach GitHub
        res["skipped"] = f"GitHub side unreachable ({e}); refusing to prune"
        return res
    try:
        hf_files = fetch_hf(hf_repo, ref)
    except Exception as e:  # noqa: BLE001 -- any failure to reach HF
        res["skipped"] = f"HF side unreachable ({e}); refusing to prune"
        return res

    remove, keep = classify_entries(accepted, gh_files, hf_files)
    res["removed"] = remove
    res["kept"] = keep
    if remove:
        res["new_allow"] = prune_allowlist(allow, remove)
    return res


# --------------------------------------------------------------------------- #
# GitHub write helpers (REST for refs/PRs, GraphQL for the SIGNED commit).
# --------------------------------------------------------------------------- #
def _token():
    return os.environ.get("SZL_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")


def _gh_request(method, url, token, body=None, accept="application/vnd.github+json"):
    hdrs = dict(UA)
    hdrs["Accept"] = accept
    hdrs["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"message": raw.decode("utf-8", "replace")}
        return e.code, payload


def gh_graphql(token, query, variables):
    status, payload = _gh_request("POST", f"{GH_API}/graphql", token,
                                  body={"query": query, "variables": variables})
    if status != 200:
        raise RuntimeError(f"GraphQL HTTP {status}: {payload}")
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def get_branch_head(owner_repo, branch, token):
    status, payload = _gh_request(
        "GET", f"{GH_API}/repos/{owner_repo}/git/ref/heads/{branch}", token)
    if status == 404:
        return None
    if status != 200:
        raise RuntimeError(f"read ref {owner_repo}@{branch}: HTTP {status}: {payload}")
    return payload["object"]["sha"]


def ensure_branch_at(owner_repo, branch, base_sha, token):
    """Create the PR branch at ``base_sha`` if absent, else fast-reset it there
    (force) so the prune commit always lands cleanly on top of current main."""
    head = get_branch_head(owner_repo, branch, token)
    if head is None:
        status, payload = _gh_request(
            "POST", f"{GH_API}/repos/{owner_repo}/git/refs", token,
            body={"ref": f"refs/heads/{branch}", "sha": base_sha})
        if status not in (200, 201):
            raise RuntimeError(f"create branch {branch}: HTTP {status}: {payload}")
        return base_sha
    if head != base_sha:
        status, payload = _gh_request(
            "PATCH", f"{GH_API}/repos/{owner_repo}/git/refs/heads/{branch}", token,
            body={"sha": base_sha, "force": True})
        if status != 200:
            raise RuntimeError(f"reset branch {branch}: HTTP {status}: {payload}")
    return base_sha


def signed_commit(owner_repo, branch, expected_head, path, contents,
                  headline, body, token):
    """Create a GitHub-signed commit on ``branch`` via createCommitOnBranch."""
    mutation = """
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) { commit { oid url } }
    }"""
    message = headline + "\n\n" + body
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": owner_repo,
                "branchName": branch,
            },
            "message": {"headline": headline, "body": body},
            "expectedHeadOid": expected_head,
            "fileChanges": {
                "additions": [{
                    "path": path,
                    "contents": base64.b64encode(contents.encode()).decode(),
                }],
            },
        }
    }
    data = gh_graphql(token, mutation, variables)
    return data["createCommitOnBranch"]["commit"]


def open_or_update_pr(owner_repo, branch, base, title, body, token):
    """Open a PR branch->base, or update the body of the existing open PR."""
    owner = owner_repo.split("/", 1)[0]
    status, payload = _gh_request(
        "POST", f"{GH_API}/repos/{owner_repo}/pulls", token,
        body={"title": title, "head": branch, "base": base, "body": body})
    if status in (200, 201):
        return payload["html_url"], "opened"
    # 422 => a PR already exists for this head; update it.
    status2, existing = _gh_request(
        "GET",
        f"{GH_API}/repos/{owner_repo}/pulls?state=open&head={owner}:{branch}",
        token)
    if status2 == 200 and existing:
        num = existing[0]["number"]
        _gh_request("PATCH", f"{GH_API}/repos/{owner_repo}/pulls/{num}", token,
                    body={"title": title, "body": body})
        return existing[0]["html_url"], "updated"
    raise RuntimeError(f"open PR for {owner_repo}: HTTP {status}: {payload}")


# --------------------------------------------------------------------------- #
# PR text
# --------------------------------------------------------------------------- #
def _commit_messages(plan):
    n = len(plan["removed"])
    plural = "y" if n == 1 else "ies"
    headline = f"chore(hf-drift): auto-prune {n} reconciled allowlist entr{plural}"
    lines = [
        "The following GitHub<->HF module-drift allowlist entries are now",
        "byte-identical on both sides (GitHub git-blob sha == live HF Space",
        "tree oid), so the suppression is stale and is removed. Any FUTURE",
        "re-divergence of these files will correctly fail the drift gate again.",
        "",
    ]
    for p in plan["removed"]:
        lines.append(f"  - {p}")
    lines += [
        "",
        "ignore_paths / ignore_extensions are left untouched; still-divergent",
        "entries are retained. Generated by hf_module_drift_prune.py.",
        "",
        f"Signed-off-by: {SIGNOFF_NAME} <{SIGNOFF_EMAIL}>",
    ]
    return headline, "\n".join(lines)


def _pr_body(plan):
    headline, body = _commit_messages(plan)
    kept = plan["kept"]
    parts = [
        "## Automated HF module-drift allowlist prune",
        "",
        f"`{plan['github']}` <-> `{plan['hf']}` ({plan['ref']})",
        "",
        "These `accepted_divergences` entries are now **byte-identical** on "
        "both sides and are removed so the allowlist stops over-counting "
        "resolved drift:",
        "",
    ]
    for p in plan["removed"]:
        parts.append(f"- `{p}`")
    if kept:
        parts += ["", "Still suppressed (NOT removed):", ""]
        for p, reason in kept.items():
            parts.append(f"- `{p}` — {reason}")
    parts += [
        "",
        "`ignore_paths` / `ignore_extensions` are untouched. Opened by the "
        "scheduled `hf-module-drift-prune` janitor; the commit is "
        "GitHub-signed via `createCommitOnBranch`.",
    ]
    return "\n".join(parts)


def apply_plan(plan, branch, allow_path, token):
    """Open/update a signed PR removing the reconciled entries for one repo."""
    owner_repo = plan["github"]
    ref = plan["ref"]
    base_head = get_branch_head(owner_repo, ref, token)
    if base_head is None:
        raise RuntimeError(f"cannot read base branch {owner_repo}@{ref}")
    ensure_branch_at(owner_repo, branch, base_head, token)
    headline, commit_body = _commit_messages(plan)
    contents = serialize_allow(plan["new_allow"])
    commit = signed_commit(owner_repo, branch, base_head, allow_path,
                           contents, headline, commit_body, token)
    url, action = open_or_update_pr(owner_repo, branch, ref, headline,
                                    _pr_body(plan), token)
    return {"commit": commit.get("oid"), "pr_url": url, "pr_action": action}


# --------------------------------------------------------------------------- #
# Orchestration over the registry
# --------------------------------------------------------------------------- #
def run(args):
    with open(args.registry) as fh:
        reg = json.load(fh)
    entries = reg.get("spaces", [])
    if not entries:
        print(f"No registry entries in {args.registry}; nothing to prune.")
        return 0

    token = _token()
    if args.apply and not token:
        print("::error::--apply requires SZL_GITHUB_TOKEN (or GITHUB_TOKEN) to "
              "open the prune PR.")
        return 1

    results = []
    pruned_repos = 0
    failed = 0
    for ent in entries:
        gh = ent.get("github")
        hf = ent.get("hf")
        ref = ent.get("ref", args.ref)
        if not gh or not hf:
            print(f"::warning::registry entry missing github/hf: {ent!r}")
            continue

        allow = checker.fetch_remote_allow(gh, ref, args.allow_path)
        plan = plan_repo(gh, hf, ref, allow)

        print(f"\n== {gh}  <->  {hf} ({ref}) ==")
        print(f"   accepted_divergences: {plan['accepted_count']}")
        if plan["skipped"]:
            print(f"::warning title=HF drift prune::{gh}: {plan['skipped']}")
        if not plan["removed"]:
            print("   nothing to prune (no entry is byte-identical yet)." )
        else:
            print(f"   reconciled (will remove {len(plan['removed'])}):")
            for p in plan["removed"]:
                print(f"     - {p}")
        for p, reason in plan["kept"].items():
            print(f"   keep: {p} -- {reason}")

        entry_result = {k: plan[k] for k in
                        ("github", "hf", "ref", "accepted_count",
                         "removed", "kept", "skipped")}
        if plan["removed"] and args.apply:
            try:
                applied = apply_plan(plan, args.branch, args.allow_path, token)
                entry_result["applied"] = applied
                pruned_repos += 1
                print(f"   PR {applied['pr_action']}: {applied['pr_url']}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                entry_result["apply_error"] = str(e)
                print(f"::error title=HF drift prune::{gh}: could not open prune "
                      f"PR: {e}")
        elif plan["removed"]:
            pruned_repos += 1  # would-prune count in report-only mode
        results.append(entry_result)

    combined = {
        "schema": 1,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "registry": args.registry,
        "applied": bool(args.apply),
        "repos_with_prunes": pruned_repos,
        "repos_failed": failed,
        "repos": results,
    }
    if args.report_out:
        with open(args.report_out, "w") as fh:
            json.dump(combined, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"\nreport written: {args.report_out}")

    verb = "pruned" if args.apply else "would prune"
    print(f"\n== HF module-drift allowlist prune: {verb} {pruned_repos} repo(s), "
          f"{failed} failure(s) ==")
    if failed:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default=".github/data/hf_space_registry.json",
                    help="JSON map of {spaces:[{github,hf,ref?}]}")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--allow-path", default=DEFAULT_ALLOW_PATH,
                    help="per-repo allowlist path inside each repo")
    ap.add_argument("--branch", default=DEFAULT_BRANCH,
                    help="branch name for the auto-prune PR")
    ap.add_argument("--apply", action="store_true",
                    help="actually open/update the signed prune PR(s); "
                         "default is report-only")
    ap.add_argument("--report-out", default="")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
