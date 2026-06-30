#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
"""
Canonical, reusable GitHub -> Hugging Face Space DEPLOYER (no bandaids).

A Hugging Face docker Space is built by Dockerfile `COPY` from its GitHub
source-of-truth. The legacy a11oy hf-sync.yml mirrored a HAND-MAINTAINED
allowlist of file paths (CATHEDRAL_FILES) that grew by one entry every time a
newly-served file fell outside the glob -- an accreting bandaid. This deployer
removes the allowlist entirely: it DERIVES the exact file set to push from the
Dockerfile's own `COPY` sources, the same derivation the org's drift-checker
(hf_module_drift_check.py) already uses to decide what to compare. The Dockerfile
is the single source of truth for "what the Space is made of", so the deploy set
can never silently drift from what the image actually builds.

Two modes:
  deploy  (default): parse Dockerfile COPY sources, expand to tracked files,
                     push them (+ README with preserved HF front-matter) to the
                     Space via huggingface_hub create_commit (add + optional
                     prune of managed files gone from git). Emits a manifest
                     (path -> {git_blob_sha1, sha256, size}).
  attest  (--attest): re-fetch every manifest path from the live Space
                      resolve/main URL and assert sha256 == the value pushed.
                      Fails loudly on any mismatch. This is the "can never drift
                      again" guard that runs after the Space finishes rebuilding.

Design notes:
  * EXCLUDES `COPY --from=<stage>` (build-stage artifacts, not repo files) and a
    bare `COPY . <dest>` whole-context copy (the Dockerfiles deliberately never
    use it; a whole-repo mirror is not a curated Space deploy). Both are skipped
    with a warning rather than silently expanded.
  * Directory COPY sources expand to every tracked file under them; globs expand
    by fnmatch; explicit files are taken as-is.
  * README front-matter is PRESERVED (the GitHub README already carries the HF
    `sdk: docker` / `app_port` card). HF's flaky server-side `_validate_yaml` is
    monkeypatched non-fatal (the documented a11oy `_safe_validate` shim).
  * stdlib-only for derivation + attestation, so --dry-run and --attest run on a
    bare runner; huggingface_hub is imported lazily only for an actual push.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HF_HOST = "https://huggingface.co"
UA = {"User-Agent": "hf-deploy-from-dockerfile/1.0"}


# --------------------------------------------------------------------------- #
# git blob sha1 (content identity, matches GitHub/HF tree OIDs)
# --------------------------------------------------------------------------- #
def git_blob_sha1(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\0")
    h.update(data)
    return h.hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Dockerfile COPY parsing (shared logic with hf_module_drift_check.py)
# --------------------------------------------------------------------------- #
def parse_copy_sources(dockerfile_text):
    """Return COPY/ADD *source* tokens. Joins line-continuations, handles the
    JSON-array form, drops --flag options, SKIPS `--from=` build-stage copies and
    a bare `.` whole-context source."""
    logical = []
    buf = ""
    for raw in dockerfile_text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not buf and (stripped.startswith("#") or stripped == ""):
            continue
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        buf += line
        logical.append(buf)
        buf = ""
    if buf:
        logical.append(buf)

    sources = []
    skipped_whole_context = False
    for line in logical:
        m = re.match(r"^\s*(COPY|ADD)\s+(.*)$", line, re.IGNORECASE)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.startswith("["):
            try:
                arr = json.loads(rest)
            except json.JSONDecodeError:
                continue
            if len(arr) >= 2:
                sources.extend(arr[:-1])
            continue
        toks = rest.split()
        skip = False
        clean = []
        for t in toks:
            if t.startswith("--"):
                if t.lower().startswith("--from"):
                    skip = True
                continue
            clean.append(t)
        if skip or len(clean) < 2:
            continue
        srcs = clean[:-1]
        # Skip a whole-context copy (`COPY . <dest>`): not a curated Space deploy.
        if any(s in (".", "./") for s in srcs):
            skipped_whole_context = True
            continue
        sources.extend(srcs)

    out, seen = [], set()
    for s in sources:
        s = s.strip()
        # Strip a literal leading "./" only -- NOT arbitrary leading "."/"/"
        # chars, or a dotdir source like ".compliance/x" collapses to "compliance/x".
        while s.startswith("./"):
            s = s[2:]
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    if skipped_whole_context:
        print("::warning::skipped a bare `COPY . <dest>` whole-context copy "
              "(deployer derives a curated per-file set, not a whole-repo mirror)")
    return out


# --------------------------------------------------------------------------- #
# Local checkout -> path -> blob sha1 (the GitHub source-of-truth side)
# --------------------------------------------------------------------------- #
def local_tree(repo_root):
    out = {}
    root = os.path.abspath(repo_root)
    for dirpath, dirnames, filenames in os.walk(root):
        parts = dirpath.split(os.sep)
        if ".git" in parts:
            continue
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, "rb") as fh:
                    out[rel] = git_blob_sha1(fh.read())
            except OSError:
                continue
    return out


def expand_sources(sources, tree):
    """COPY sources (file / dir / glob) -> concrete tracked file set, with the
    matched COPY source recorded per file so prune can scope to managed dirs."""
    paths = set(tree)
    targets = {}
    unresolved = []
    for src in sources:
        s = src.rstrip("/")
        if s in paths:
            targets[s] = s
            continue
        pref = s + "/"
        members = {p for p in paths if p.startswith(pref)}
        if members:
            for m in members:
                targets[m] = s
            continue
        if any(ch in s for ch in "*?["):
            globbed = {p for p in paths if fnmatch.fnmatch(p, s)}
            if globbed:
                for g in globbed:
                    targets[g] = s
                continue
        unresolved.append(src)
    return targets, unresolved


# --------------------------------------------------------------------------- #
# README front-matter preservation
# --------------------------------------------------------------------------- #
def load_readme(path):
    """Return README bytes. Front-matter (--- ... ---) is preserved verbatim; we
    only assert it carries `sdk: docker` so the Space does not CONFIG_ERROR."""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8", "replace")
    if text.startswith("---"):
        seg = text.split("\n---", 1)
        fm = seg[0]
        if "sdk:" not in fm:
            print("::warning::README front-matter has no `sdk:` line; HF Space "
                  "may CONFIG_ERROR (founder: confirm the Space card).")
    else:
        print("::warning::README has NO YAML front-matter; HF docker Space "
              "REQUIRES `sdk: docker` + `app_port`. Pushing as-is (founder action: "
              "add front-matter to README.md).")
    return raw


# --------------------------------------------------------------------------- #
# HF HTTP (stdlib, retry) -- for attestation + tree listing
# --------------------------------------------------------------------------- #
def _http(url, headers=None, retries=6):
    last = None
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return e.code, b""
            last = e
            if e.code == 429 or 500 <= e.code < 600:
                ra = (e.headers or {}).get("Retry-After")
                try:
                    delay = float(ra) if ra else min(60.0, 2.0 * (2 ** attempt))
                except ValueError:
                    delay = min(60.0, 2.0 * (2 ** attempt))
                time.sleep(delay + random.uniform(0, 1.0))
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1) + random.uniform(0, 0.5))
    raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")


def hf_resolve(hf_repo, path, ref="main"):
    url = f"{HF_HOST}/spaces/{hf_repo}/resolve/{ref}/{urllib.parse.quote(path)}"
    return _http(url, headers=_auth_headers())


def _auth_headers():
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def hf_runtime_stage(hf_repo):
    url = f"{HF_HOST}/api/spaces/{hf_repo}"
    try:
        status, body = _http(url, headers=_auth_headers())
    except RuntimeError:
        return None
    if status != 200:
        return None
    try:
        return (json.loads(body).get("runtime") or {}).get("stage")
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# derive: Dockerfile -> deploy manifest (no network, no push)
# --------------------------------------------------------------------------- #
def derive(args):
    df_path = args.dockerfile_path
    if not os.path.isabs(df_path):
        df_path = os.path.join(args.repo_root, df_path)
    with open(df_path, "rb") as fh:
        dockerfile_text = fh.read().decode("utf-8", "replace")
    sources = parse_copy_sources(dockerfile_text)
    tree = local_tree(args.repo_root)
    targets, unresolved = expand_sources(sources, tree)

    if unresolved:
        for u in unresolved:
            print(f"::warning::COPY source not found in checkout (skipped): {u}")

    files = {}
    for rel, src in sorted(targets.items()):
        full = os.path.join(args.repo_root, rel)
        with open(full, "rb") as fh:
            data = fh.read()
        files[rel] = {
            "git_blob_sha1": git_blob_sha1(data),
            "sha256": sha256(data),
            "size": len(data),
            "copy_source": src,
        }

    readme_rel = None
    if args.include_readme:
        rp = os.path.join(args.repo_root, args.readme_path)
        if os.path.exists(rp):
            data = load_readme(rp)
            readme_rel = args.readme_path
            files[readme_rel] = {
                "git_blob_sha1": git_blob_sha1(data),
                "sha256": sha256(data),
                "size": len(data),
                "copy_source": "(readme)",
            }
        else:
            print(f"::warning::--include-readme set but {rp} not found")

    manifest = {
        "schema": 1,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "github_repo": args.github_repo,
        "hf_repo": args.hf_repo,
        "ref": args.ref,
        "dockerfile": args.dockerfile_path,
        "copy_sources": len(sources),
        "files_resolved": len(targets),
        "unresolved_sources": unresolved,
        "readme": readme_rel,
        "files": files,
    }
    return manifest, files


# --------------------------------------------------------------------------- #
# deploy: push the derived set (add + optional prune) via huggingface_hub
# --------------------------------------------------------------------------- #
def deploy(args):
    manifest, files = derive(args)
    print(f"== HF deploy: {args.github_repo} -> {args.hf_repo} ({args.ref}) ==")
    print(f"   COPY sources: {manifest['copy_sources']}   files resolved: "
          f"{manifest['files_resolved']}   readme: {manifest['readme']}")
    for p in sorted(files):
        print(f"   + {p}  ({files[p]['size']}B  blob {files[p]['git_blob_sha1'][:12]})")

    if args.manifest_out:
        with open(args.manifest_out, "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"   manifest -> {args.manifest_out}")

    if args.dry_run:
        print("\nDRY RUN: derivation + manifest only; no push performed.")
        return 0

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("::error::HF_TOKEN not set -- cannot push to the Space.")
        print("::error::Founder action: add repo/org secret HF_TOKEN (HF write token).")
        return 2

    from huggingface_hub import (HfApi, CommitOperationAdd,  # lazy import
                                 CommitOperationDelete)

    # HF's server-side README YAML validator intermittently returns non-JSON and
    # aborts an otherwise-valid commit; make it non-fatal (documented a11oy shim).
    _orig = HfApi._validate_yaml
    def _safe_validate(self, content, *a, **k):
        try:
            return _orig(self, content, *a, **k)
        except Exception as e:  # noqa: BLE001
            print("::warning::HF _validate_yaml skipped (non-fatal):", repr(e)[:160])
            return None
    HfApi._validate_yaml = _safe_validate

    api = HfApi(token=token)
    ops = []
    for rel in sorted(files):
        with open(os.path.join(args.repo_root, rel), "rb") as fh:
            ops.append(CommitOperationAdd(path_in_repo=rel, path_or_fileobj=fh.read()))

    deleted = []
    if args.prune:
        managed_dirs = {f["copy_source"] for f in files.values()
                        if f["copy_source"] not in ("(readme)",)
                        and "/" in f["copy_source"] + "/"  # any source
                        }
        # Only prune within COPY sources that are DIRECTORIES (whole-dir managed),
        # never within file/glob sources -- avoids sweeping Space-only vendor blobs.
        dir_sources = set()
        df_path = args.dockerfile_path
        if not os.path.isabs(df_path):
            df_path = os.path.join(args.repo_root, df_path)
        for src in parse_copy_sources(open(df_path, encoding="utf-8", errors="replace").read()):
            s = src.rstrip("/")
            # a dir source is one where the checkout has children under s/
            if any(p.startswith(s + "/") for p in files):
                dir_sources.add(s + "/")
        live = api.list_repo_files(repo_id=args.hf_repo, repo_type="space")
        local_set = set(files)
        for p in live:
            if p in local_set:
                continue
            if any(p.startswith(ds) for ds in dir_sources):
                ops.append(CommitOperationDelete(path_in_repo=p))
                deleted.append(p)

    commit = api.create_commit(
        repo_id=args.hf_repo, repo_type="space", operations=ops,
        commit_message=f"deploy(hf): sync {args.github_repo}@{args.ref} derived COPY set",
        commit_description=(
            f"Reusable Dockerfile-COPY-derived deploy from {args.github_repo} {args.ref}.\n"
            f"Files: {len(files)}  Pruned: {len(deleted)}\n"
            "Derived from Dockerfile COPY sources (NO hand-maintained allowlist).\n\n"
            "Signed-off-by: SZL Holdings <noreply@szlholdings.ai>\n"
            "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"),
    )
    print(f"\nHF commit: {commit.oid} -> {args.hf_repo}  added:{len(files)} pruned:{len(deleted)}")
    manifest["hf_commit_oid"] = commit.oid
    manifest["pruned"] = deleted
    if args.manifest_out:
        with open(args.manifest_out, "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return 0


# --------------------------------------------------------------------------- #
# attest: re-fetch each pushed file from the live Space and verify sha256
# --------------------------------------------------------------------------- #
def attest(args):
    with open(args.manifest) as fh:
        manifest = json.load(fh)
    hf_repo = args.hf_repo or manifest.get("hf_repo")
    ref = args.ref or manifest.get("ref", "main")
    files = manifest.get("files", {})
    if not hf_repo or not files:
        print("::error::attest needs a manifest with hf_repo + files")
        return 2

    # Wait for the Space to finish rebuilding before re-fetching.
    if args.wait_running:
        deadline = time.time() + args.wait_running
        while time.time() < deadline:
            stage = hf_runtime_stage(hf_repo)
            print(f"   runtime stage: {stage}")
            if stage in ("RUNNING", "RUNNING_APP_STARTING"):
                break
            if stage in ("BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR"):
                print(f"::error::Space {hf_repo} in {stage} -- deploy did not come up.")
                return 1
            time.sleep(15)

    mism, missing, ok = [], [], 0
    for path, meta in sorted(files.items()):
        want = meta.get("sha256")
        try:
            status, body = hf_resolve(hf_repo, path, ref)
        except RuntimeError as e:
            missing.append((path, f"fetch-failed: {e}"))
            continue
        if status != 200:
            missing.append((path, f"HTTP {status}"))
            continue
        got = sha256(body)
        if got == want:
            ok += 1
        else:
            mism.append((path, want, got))

    print(f"\n== HF deploy attestation: {hf_repo} ({ref}) ==")
    print(f"   verified OK: {ok}   mismatched: {len(mism)}   missing: {len(missing)}")
    for p, w, g in mism:
        print(f"::error title=HF deploy drift::{p}: sha256 mismatch "
              f"git={w[:16]} live={g[:16]}")
    for p, why in missing:
        print(f"::error title=HF deploy missing::{p}: {why}")
    if mism or missing:
        print("\nFAIL: live Space does not match the pushed git blobs.")
        return 1
    print("\nOK: every pushed file is byte-identical on the live Space (attested).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--github-repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--hf-repo", default="")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--dockerfile-path", default="Dockerfile")
    ap.add_argument("--readme-path", default="README.md")
    ap.add_argument("--include-readme", default="true")
    ap.add_argument("--manifest-out", default="")
    ap.add_argument("--prune", action="store_true",
                    help="delete Space files under directory COPY sources that are "
                         "gone from git main (never touches file/glob sources)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--attest", action="store_true",
                    help="verification mode: re-fetch manifest files from the live "
                         "Space and assert sha256 == pushed value")
    ap.add_argument("--manifest", default="", help="manifest path (attest mode)")
    ap.add_argument("--wait-running", type=int, default=0,
                    help="attest: seconds to poll runtime stage for RUNNING first")
    args = ap.parse_args()

    args.include_readme = str(args.include_readme).lower() not in ("false", "0", "no")

    # Derive HF repo by convention if not given: szl-holdings/<x> -> SZLHOLDINGS/<x>.
    if not args.hf_repo:
        name = (args.github_repo.split("/")[-1] if args.github_repo else
                os.path.basename(os.path.abspath(args.repo_root)))
        args.hf_repo = f"SZLHOLDINGS/{name}"

    if args.attest:
        if not args.manifest:
            ap.error("--attest requires --manifest")
        return attest(args)
    return deploy(args)


if __name__ == "__main__":
    sys.exit(main())
