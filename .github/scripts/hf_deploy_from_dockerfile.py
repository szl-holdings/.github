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
                     push them (+ the build Dockerfile at HF-root `Dockerfile`
                     and optional README) to the Space via huggingface_hub
                     create_commit. Emits a source-aware manifest.
  attest  (--attest): require the Space API to report the exact pushed HF commit
                      in RUNNING state, re-fetch every manifest path at that
                      immutable commit, and probe declared same-host live routes.

Design notes:
  * EXCLUDES `COPY --from=<stage>` (build-stage artifacts, not repo files). A
    bare `COPY . <dest>` whole-context copy and every unresolved COPY source are
    hard errors: the deployer never publishes a knowingly incomplete manifest.
  * Directory COPY sources expand to every tracked file under them; globs expand
    by fnmatch; explicit files are taken as-is.
  * README is deployed iff `--include-readme` is true, even when a Dockerfile
    explicitly COPYs it. When included, its front-matter is PRESERVED (the
    GitHub README already carries the HF `sdk: docker` / `app_port` card). HF's
    flaky server-side `_validate_yaml` is monkeypatched non-fatal (the documented
    a11oy `_safe_validate` shim).
  * stdlib-only for derivation + attestation, so --dry-run and --attest run on a
    bare runner; huggingface_hub is imported lazily only for an actual push.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HF_HOST = "https://huggingface.co"
UA = {"User-Agent": "hf-deploy-from-dockerfile/1.0"}
TERMINAL_RUNTIME_STAGES = {"BUILD_ERROR", "CONFIG_ERROR", "RUNTIME_ERROR"}


class DeployContractError(ValueError):
    """The requested deployment cannot produce a complete, safe manifest."""


def normalize_repo_path(path, *, label="repository path"):
    """Return a safe forward-slash path contained by the repository root."""
    value = str(path or "").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    value = posixpath.normpath(value)
    if (value in ("", ".") or value.startswith("/") or
            re.match(r"^[A-Za-z]:/", value)):
        raise DeployContractError(f"{label} must be a non-empty relative path: {path!r}")
    if value == ".." or value.startswith("../"):
        raise DeployContractError(f"{label} escapes the repository root: {path!r}")
    return value


def source_file(repo_root, source_path):
    """Resolve a manifest source path and fail if it escapes the checkout."""
    rel = normalize_repo_path(source_path, label="source_path")
    root = os.path.realpath(repo_root)
    full = os.path.realpath(os.path.join(root, *rel.split("/")))
    try:
        contained = os.path.commonpath((root, full)) == root
    except ValueError:
        contained = False
    if not contained:
        raise DeployContractError(f"source_path escapes the repository root: {rel!r}")
    if not os.path.isfile(full):
        raise DeployContractError(f"source_path is not a file in the checkout: {rel!r}")
    return rel, full


def read_source_bytes(repo_root, target_path, meta):
    """Read the GitHub source mapped to an HF target path."""
    source_path = meta.get("source_path") or target_path
    _, full = source_file(repo_root, source_path)
    with open(full, "rb") as fh:
        return fh.read()


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
    JSON-array form, drops --flag options, and SKIPS `--from=` build-stage
    copies. A whole-context source is rejected because it cannot be represented
    as a curated, independently attestable deploy set."""
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
    for line in logical:
        m = re.match(r"^\s*(COPY|ADD)\s+(.*)$", line, re.IGNORECASE)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.startswith("["):
            try:
                arr = json.loads(rest)
            except json.JSONDecodeError as exc:
                raise DeployContractError(
                    f"malformed JSON-form Dockerfile instruction: {line.strip()}"
                ) from exc
            if not isinstance(arr, list) or len(arr) < 2 or not all(
                isinstance(item, str) for item in arr
            ):
                raise DeployContractError(
                    f"invalid JSON-form Dockerfile instruction: {line.strip()}"
                )
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
        if skip:
            continue
        if len(clean) < 2:
            raise DeployContractError(
                f"COPY/ADD instruction has no complete source/destination pair: "
                f"{line.strip()}"
            )
        srcs = clean[:-1]
        for source in srcs:
            normalized = source
            while normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized in ("", "."):
                raise DeployContractError(
                    "bare `COPY . <dest>` / `ADD . <dest>` is forbidden: "
                    "the deployer requires an explicit curated source set"
                )
        sources.extend(srcs)

    out, seen = [], set()
    for s in sources:
        s = s.strip()
        # Strip a literal leading "./" only -- NOT arbitrary leading "."/"/"
        # chars, or a dotdir source like ".compliance/x" collapses to "compliance/x".
        while s.startswith("./"):
            s = s[2:]
        if s in ("", "."):
            raise DeployContractError(
                "bare `COPY . <dest>` / `ADD . <dest>` is forbidden: "
                "the deployer requires an explicit curated source set"
            )
        if s and s not in seen:
            seen.add(s)
            out.append(s)
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
# HF HTTP (stdlib, retry) -- for attestation + live route closure
# --------------------------------------------------------------------------- #
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http(url, headers=None, retries=6, follow_redirects=True):
    last = None
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    opener = (urllib.request.build_opener() if follow_redirects else
              urllib.request.build_opener(_NoRedirect()))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with opener.open(req, timeout=45) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 500:
                return e.code, e.read()
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


def hf_space_state(hf_repo):
    """Return the public Space API's exact (stage, sha) deployment identity."""
    url = f"{HF_HOST}/api/spaces/{hf_repo}"
    status, body = _http(url, headers=_auth_headers())
    if status != 200:
        raise RuntimeError(f"Space API returned HTTP {status}: {url}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Space API returned invalid JSON: {url}") from exc
    return (payload.get("runtime") or {}).get("stage"), payload.get("sha")


def normalize_smoke_paths(value=None):
    """Validate relative live-app paths; callers can never select another host."""
    if value is None or value == "":
        raw_paths = ["/"]
    elif isinstance(value, str):
        try:
            raw_paths = json.loads(value)
        except json.JSONDecodeError as exc:
            raise DeployContractError(
                "--smoke-paths must be a JSON array of same-host absolute paths"
            ) from exc
    else:
        raw_paths = value
    if not isinstance(raw_paths, list) or not raw_paths:
        raise DeployContractError("smoke_paths must be a non-empty JSON array")

    paths, seen = [], set()
    for raw in raw_paths:
        if not isinstance(raw, str) or not raw:
            raise DeployContractError("each smoke path must be a non-empty string")
        if "\\" in raw or any(ord(ch) < 32 for ch in raw):
            raise DeployContractError(f"unsafe smoke path: {raw!r}")
        parsed = urllib.parse.urlsplit(raw)
        if (parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or
                parsed.path.startswith("//") or parsed.fragment):
            raise DeployContractError(
                f"smoke path must be same-host, absolute-path-only, and fragment-free: {raw!r}"
            )
        normalized = urllib.parse.urlunsplit(("", "", parsed.path,
                                              parsed.query, ""))
        if normalized not in seen:
            seen.add(normalized)
            paths.append(normalized)
    return paths


def hf_live_origin(hf_repo):
    parts = hf_repo.split("/")
    if len(parts) != 2 or not all(parts):
        raise DeployContractError(
            f"HF Space id must be exactly <owner>/<name>: {hf_repo!r}"
        )
    subdomain = re.sub(r"[^a-z0-9-]+", "-", "-".join(parts).lower()).strip("-")
    if not subdomain:
        raise DeployContractError(f"HF Space id has no usable app hostname: {hf_repo!r}")
    return f"https://{subdomain}.hf.space"


def wait_for_expected_runtime(hf_repo, expected_sha, timeout, poll_interval=15):
    """Require the exact pushed commit to reach the exact RUNNING stage."""
    timeout = max(0, int(timeout or 0))
    deadline = time.monotonic() + timeout
    first = True
    last_stage = last_sha = None
    last_error = None
    while first or time.monotonic() < deadline:
        first = False
        try:
            last_stage, last_sha = hf_space_state(hf_repo)
            last_error = None
            print(f"   runtime stage: {last_stage}   api sha: {last_sha}")
            if last_stage == "RUNNING" and last_sha == expected_sha:
                return True
            if last_sha == expected_sha and last_stage in TERMINAL_RUNTIME_STAGES:
                print(f"::error::Space {hf_repo}@{expected_sha} is in {last_stage}.")
                return False
        except RuntimeError as exc:
            last_error = str(exc)
            print(f"::warning::Space runtime identity unavailable: {last_error}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(float(poll_interval), remaining))

    detail = (f"last stage={last_stage!r} sha={last_sha!r}" if not last_error
              else f"last error={last_error}")
    print(f"::error::Timed out waiting for {hf_repo} to report exact RUNNING "
          f"commit {expected_sha}; {detail}")
    return False


def probe_smoke_routes(hf_repo, smoke_paths, retries=6, delay=5):
    """Probe only the derived Space host; redirects and empty bodies fail."""
    paths = normalize_smoke_paths(smoke_paths)
    origin = hf_live_origin(hf_repo)
    failures = []
    for path in paths:
        url = origin + path
        last_status = None
        last_detail = "not attempted"
        for attempt in range(max(1, int(retries))):
            try:
                status, body = _http(
                    url, headers=_auth_headers(), retries=1,
                    follow_redirects=False,
                )
                last_status = status
                last_detail = f"HTTP {status}, {len(body)} bytes"
                if status == 200 and body:
                    print(f"   smoke OK: {path} (HTTP 200, {len(body)} bytes)")
                    break
            except RuntimeError as exc:
                last_detail = str(exc)
            if attempt + 1 < max(1, int(retries)):
                time.sleep(float(delay))
        else:
            failures.append((path, last_status, last_detail))
    return failures


# --------------------------------------------------------------------------- #
# derive: Dockerfile -> deploy manifest (no network, no push)
# --------------------------------------------------------------------------- #
def derive(args):
    dockerfile_rel, df_path = source_file(args.repo_root, args.dockerfile_path)
    with open(df_path, "rb") as fh:
        dockerfile_text = fh.read().decode("utf-8", "replace")
    sources = parse_copy_sources(dockerfile_text)
    tree = local_tree(args.repo_root)
    targets, unresolved = expand_sources(sources, tree)

    # include-readme is authoritative. A README may already be in the derived
    # set because the Dockerfile explicitly COPYs it; remove that exact path
    # when the caller owns the Space card separately. Normalize the CLI path to
    # the forward-slash form used by local_tree/expand_sources, without filtering
    # unrelated nested README files.
    readme_path = normalize_repo_path(args.readme_path, label="README source path")
    if not args.include_readme:
        targets.pop(readme_path, None)

    if unresolved:
        raise DeployContractError(
            "Dockerfile COPY/ADD sources were not found in the checkout: "
            + ", ".join(sorted(unresolved))
        )

    files = {}
    for rel, src in sorted(targets.items()):
        data = read_source_bytes(args.repo_root, rel, {"source_path": rel})
        files[rel] = {
            "git_blob_sha1": git_blob_sha1(data),
            "sha256": sha256(data),
            "size": len(data),
            "copy_source": src,
            "source_path": rel,
        }

    readme_rel = None
    if args.include_readme:
        _, rp = source_file(args.repo_root, readme_path)
        data = load_readme(rp)
        readme_rel = readme_path
        files[readme_rel] = {
            "git_blob_sha1": git_blob_sha1(data),
            "sha256": sha256(data),
            "size": len(data),
            "copy_source": "(readme)",
            "source_path": readme_rel,
        }

    # The Space build always consumes an HF-root Dockerfile. It is therefore a
    # first-class deployed artifact even though Dockerfiles do not COPY
    # themselves. `source_path` preserves nested caller layouts such as yarqa's
    # `space/Dockerfile` while the target remains exactly `Dockerfile` on HF.
    dockerfile_bytes = read_source_bytes(
        args.repo_root, "Dockerfile", {"source_path": dockerfile_rel}
    )
    files["Dockerfile"] = {
        "git_blob_sha1": git_blob_sha1(dockerfile_bytes),
        "sha256": sha256(dockerfile_bytes),
        "size": len(dockerfile_bytes),
        "copy_source": "(dockerfile)",
        "source_path": dockerfile_rel,
    }

    smoke_paths = normalize_smoke_paths(getattr(args, "smoke_paths", None))

    manifest = {
        "schema": 2,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "github_repo": args.github_repo,
        "hf_repo": args.hf_repo,
        "ref": args.ref,
        "dockerfile": dockerfile_rel,
        "dockerfile_target": "Dockerfile",
        "copy_sources": len(sources),
        "files_resolved": len(targets),
        "files_deployed": len(files),
        "unresolved_sources": unresolved,
        "readme": readme_rel,
        "smoke_paths": smoke_paths,
        "files": files,
    }
    return manifest, files


# --------------------------------------------------------------------------- #
# deploy: push the derived set (add + optional prune) via huggingface_hub
# --------------------------------------------------------------------------- #
def build_add_operations(repo_root, files, operation_class):
    """Build HF add operations from the exact source bytes the manifest hashed."""
    operations = []
    for target_path in sorted(files):
        meta = files[target_path]
        data = read_source_bytes(repo_root, target_path, meta)
        # Re-hash the exact source bytes used for the operation. This closes the
        # nested-Dockerfile class of bugs where the manifest hashed one path but
        # the deploy operation opened another.
        if sha256(data) != meta.get("sha256"):
            raise DeployContractError(
                f"source changed after manifest derivation: "
                f"{meta.get('source_path', target_path)}"
            )
        operations.append(
            operation_class(path_in_repo=target_path, path_or_fileobj=data)
        )
    return operations


def deploy(args):
    manifest, files = derive(args)
    print(f"== HF deploy: {args.github_repo} -> {args.hf_repo} ({args.ref}) ==")
    print(f"   COPY sources: {manifest['copy_sources']}   files resolved: "
          f"{manifest['files_resolved']}   readme: {manifest['readme']}")
    for p in sorted(files):
        source = files[p].get("source_path", p)
        mapping = f"{source} -> {p}" if source != p else p
        print(f"   + {mapping}  ({files[p]['size']}B  "
              f"blob {files[p]['git_blob_sha1'][:12]})")

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
    ops = build_add_operations(args.repo_root, files, CommitOperationAdd)

    deleted = []
    if args.prune:
        # Only prune within COPY sources that are DIRECTORIES (whole-dir managed),
        # never within file/glob sources -- avoids sweeping Space-only vendor blobs.
        dir_sources = set()
        _, df_path = source_file(args.repo_root, args.dockerfile_path)
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
    files = manifest.get("files", {})
    if not hf_repo or not files:
        print("::error::attest needs a manifest with hf_repo + files")
        return 2

    hf_commit_oid = str(manifest.get("hf_commit_oid") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", hf_commit_oid):
        print("::error::attest requires manifest.hf_commit_oid as an exact "
              "40-character commit SHA")
        return 2
    smoke_paths = normalize_smoke_paths(manifest.get("smoke_paths", ["/"]))

    # A RUNNING old revision is not this deployment. Require both exact state
    # and exact API identity before immutable content and live routes are tested.
    if not wait_for_expected_runtime(
        hf_repo, hf_commit_oid, args.wait_running
    ):
        return 1

    mism, missing, ok = [], [], 0
    for path, meta in sorted(files.items()):
        want = meta.get("sha256")
        try:
            status, body = hf_resolve(hf_repo, path, hf_commit_oid)
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

    print(f"\n== HF deploy attestation: {hf_repo} ({hf_commit_oid}) ==")
    print(f"   verified OK: {ok}   mismatched: {len(mism)}   missing: {len(missing)}")
    for p, w, g in mism:
        print(f"::error title=HF deploy drift::{p}: sha256 mismatch "
              f"git={w[:16]} live={g[:16]}")
    for p, why in missing:
        print(f"::error title=HF deploy missing::{p}: {why}")
    if mism or missing:
        print("\nFAIL: live Space does not match the pushed git blobs.")
        return 1

    route_failures = probe_smoke_routes(
        hf_repo, smoke_paths, retries=args.smoke_retries
    )
    for path, status, detail in route_failures:
        print(f"::error title=HF live route failed::{path}: expected exact HTTP "
              f"200 with non-empty body; status={status!r}; {detail}")
    if route_failures:
        print("\nFAIL: declared live Space routes did not close after deployment.")
        return 1

    print("\nOK: exact HF commit is RUNNING, every pushed file is byte-identical, "
          "and every declared live route returns HTTP 200 with content.")
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
    ap.add_argument(
        "--smoke-paths", default='["/"]',
        help="JSON array of same-host live app paths to require after deploy",
    )
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
                    help="attest: seconds to require exact API sha + RUNNING stage")
    ap.add_argument("--smoke-retries", type=int, default=6,
                    help="attest: attempts per declared live route")
    args = ap.parse_args()

    args.include_readme = str(args.include_readme).lower() not in ("false", "0", "no")

    # Derive HF repo by convention if not given: szl-holdings/<x> -> SZLHOLDINGS/<x>.
    if not args.hf_repo:
        name = (args.github_repo.split("/")[-1] if args.github_repo else
                os.path.basename(os.path.abspath(args.repo_root)))
        args.hf_repo = f"SZLHOLDINGS/{name}"

    try:
        if args.attest:
            if not args.manifest:
                ap.error("--attest requires --manifest")
            return attest(args)
        return deploy(args)
    except DeployContractError as exc:
        print(f"::error title=HF deploy contract::{exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
