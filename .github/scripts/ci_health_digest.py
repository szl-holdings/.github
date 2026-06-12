#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © 2026 SZL Holdings — org CI-health digest + recommendations.
#
# Sweeps every active (non-archived) repo in the szl-holdings org, finds the
# latest workflow run per workflow on the repo's default branch, classifies any
# red ones by DISPOSITION, and upserts a SINGLE rolling tracking issue in
# szl-holdings/.github so the maintainer's notification inbox stays to one
# actionable item instead of dozens of scattered run-failure emails.
#
# Honest by construction: it never marks a known-intentional red as "broken",
# and never claims a founder-gated item is fixable in CI. Dispositions:
#   ACTIONABLE     — a real bug a maintainer/agent should fix.
#   FOUNDER-GATED  — blocked on a founder-only secret / account / legal action.
#   INTENTIONAL    — designed to be red (e.g. a proof gate rejecting an OPEN
#                    conjecture); leaving it red is correct.
#   INFRA          — needs dedicated infra / is dispatch-only (low/no noise).
#
# Pure stdlib (urllib + json) so it runs with no pip step. Auth: ORG_CI_READ_TOKEN
# (org-read PAT). Optional ntfy via SLACK_WEBHOOK_URL (box relay); skipped if absent.

import os, json, sys, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ORG = "szl-holdings"
TOKEN = os.environ.get("ORG_CI_READ_TOKEN") or os.environ.get("GITHUB_TOKEN")
ISSUE_TITLE = "🔴 CI Health Digest — org-wide"
ISSUE_LABEL = "ci-health"
RED = ("failure", "startup_failure", "timed_out", "action_required")

# (repo, workflow-name substring) -> (disposition, note). First match wins.
# Keep this the SINGLE place where a red is reclassified away from ACTIONABLE,
# with a reason. Do NOT silence a real bug here.
POLICY = [
    ("lambda-bounty", "verify-proof",   ("INTENTIONAL", "Proof gate rejects the still-OPEN Λ (Conjecture 1) by design — red is the honest verdict.")),
    ("szl-doctrine",  "secret-health",  ("FOUNDER-GATED", "Needs org secret SECRET_HEALTH_TOKEN (founder least-priv PAT). Cannot be minted in CI.")),
    ("",              "Dependabot Updates", ("INFRA", "Dependabot runner state, not a workflow bug; resolves when the grouped PR opens/merges.")),
    ("",              "CodeQL",         ("INFRA", "CodeQL default-setup run; reconfigure via repo Security settings, not a workflow-file fix.")),
    ("",              "ClusterFuzzLite", ("INFRA", "PR fuzzing waits on manual approval (action_required) for outside contributions.")),
    ("",              "Fuzz",           ("INFRA", "Scheduled fuzzing run; corpus/infra-driven, not a default-branch regression.")),
    ("",              "Publish npm",    ("INFRA", "Manual workflow_dispatch publish — red reflects a past manual run, not branch health.")),
    ("",              "Cosign keyless", ("INFRA", "Runs only on release events; needs a tagged release with OIDC id-token perms, not a push-time fix.")),
    ("",              "SLSA",           ("INFRA", "Provenance/attestation signing path (dispatch/push); pending wiring, not an app-code bug.")),
]

def api(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, (json.loads(r.read()) if r.length != 0 else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode("utf-8", "replace")

def classify(repo, wf):
    for rp, sub, verdict in POLICY:
        if (not rp or rp == repo) and sub.lower() in wf.lower():
            return verdict
    return ("ACTIONABLE", "")

def list_repos():
    repos, page = [], 1
    while True:
        st, r = api("https://api.github.com/orgs/%s/repos?per_page=100&type=all&page=%d" % (ORG, page))
        if not isinstance(r, list) or not r:
            break
        repos += r
        if len(r) < 100:
            break
        page += 1
    return [(x["name"], x["default_branch"]) for x in repos if not x.get("archived")]

def repo_reds(item):
    name, default = item
    out = []
    st, wfs = api("https://api.github.com/repos/%s/%s/actions/workflows?per_page=100" % (ORG, name))
    if not isinstance(wfs, dict):
        return name, out
    def latest(w):
        if w.get("state") != "active":
            return None
        for q in ("&branch=" + default, ""):
            st, rr = api("https://api.github.com/repos/%s/%s/actions/workflows/%d/runs?per_page=1%s" % (ORG, name, w["id"], q))
            runs = rr.get("workflow_runs", []) if isinstance(rr, dict) else []
            if runs:
                r = runs[0]
                if r["conclusion"] in RED:
                    return (w["name"], r["conclusion"], r["run_number"], r.get("event"), r.get("html_url"))
                return None
        return None
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(latest, wfs.get("workflows", [])):
            if res:
                out.append(res)
    return name, out

def build_body(reds):
    from datetime import datetime, timezone
    buckets = {"ACTIONABLE": [], "FOUNDER-GATED": [], "INTENTIONAL": [], "INFRA": []}
    total = 0
    for repo in sorted(reds):
        for (wf, concl, num, ev, url) in reds[repo]:
            disp, note = classify(repo, wf)
            buckets[disp].append((repo, wf, concl, num, ev, url, note))
            total += 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["_Auto-generated by `.github/workflows/ci-health-digest.yml`. Last sweep: **%s**._" % now, ""]
    act = len(buckets["ACTIONABLE"])
    lines += ["**%d red workflow(s)** across the org — **%d ACTIONABLE**, %d founder-gated, %d intentional, %d infra." % (
        total, act, len(buckets["FOUNDER-GATED"]), len(buckets["INTENTIONAL"]), len(buckets["INFRA"])), ""]
    order = [("ACTIONABLE", "### 🛠 Actionable — fix these (root-cause, no bandaids)"),
             ("FOUNDER-GATED", "### 🔑 Founder-gated — needs a founder secret/action"),
             ("INFRA", "### ⚙️ Infra / low-noise — reconfigure or ignore"),
             ("INTENTIONAL", "### ✅ Intentional — red is correct, leave as-is")]
    for key, hdr in order:
        rows = buckets[key]
        if not rows:
            continue
        lines.append(hdr)
        lines.append("")
        lines.append("| Repo | Workflow | Result | Trigger | Note |")
        lines.append("|---|---|---|---|---|")
        for repo, wf, concl, num, ev, url, note in sorted(rows):
            wfc = "[%s](%s)" % (wf, url) if url else wf
            lines.append("| `%s` | %s | %s (run#%s) | %s | %s |" % (repo, wfc, concl, num, ev or "", note))
        lines.append("")
    if total == 0:
        lines = ["_Last sweep: **%s**._" % now, "", "## ✅ All clear — no red workflows on any default branch.", ""]
    lines.append("---")
    lines.append("<sub>Dispositions are policy-classified in `.github/scripts/ci_health_digest.py` (`POLICY`). "
                 "Reclassify a red only with a documented reason; never silence a real bug.</sub>")
    return "\n".join(lines), act, total

def upsert_issue(body):
    # find existing open issue by exact title
    st, issues = api("https://api.github.com/repos/%s/.github/issues?state=open&labels=%s&per_page=50" % (ORG, ISSUE_LABEL))
    existing = None
    if isinstance(issues, list):
        for i in issues:
            if i.get("title") == ISSUE_TITLE and "pull_request" not in i:
                existing = i
                break
    if existing:
        st, _ = api("https://api.github.com/repos/%s/.github/issues/%d" % (ORG, existing["number"]), "PATCH", {"body": body})
        return "updated #%d (HTTP %s)" % (existing["number"], st)
    st, r = api("https://api.github.com/repos/%s/.github/issues" % ORG, "POST",
                {"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]})
    return "created #%s (HTTP %s)" % (r.get("number") if isinstance(r, dict) else "?", st)

def maybe_ntfy(act, total):
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        print("ntfy: skipped (SLACK_WEBHOOK_URL absent)")
        return
    msg = "SZL CI Health: %d actionable / %d red workflows org-wide." % (act, total)
    try:
        req = urllib.request.Request(hook, data=json.dumps({"text": msg}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=15)
        print("ntfy: sent")
    except Exception as e:
        print("ntfy: failed (non-fatal):", str(e)[:80])

def main():
    if not TOKEN:
        print("::error::No ORG_CI_READ_TOKEN/GITHUB_TOKEN available."); sys.exit(1)
    repos = list_repos()
    print("sweeping %d active repos..." % len(repos))
    reds = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, out in ex.map(repo_reds, repos):
            if out:
                reds[name] = out
    body, act, total = build_body(reds)
    print(upsert_issue(body))
    maybe_ntfy(act, total)
    # Write a job summary too.
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write("# CI Health Digest\n\n%s\n" % body)
    print("done: %d actionable / %d red" % (act, total))

if __name__ == "__main__":
    main()
