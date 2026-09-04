#!/usr/bin/env python3
"""Build an exact, network-free Hugging Face candidate payload plan.

The verifier reads only local Git objects for an exact base and candidate
commit.  It imports the protected production publisher's COPY expansion and
Docker-ignore matcher, but it never imports or executes candidate code and it
never contacts GitHub, Hugging Face, or a live runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import hf_deploy_from_dockerfile as publisher


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TREE_META_RE = re.compile(rb"^([0-7]{6}) (blob|commit) ([0-9a-f]{40})$")
SAFE_BLOB_MODES = {"100644", "100755"}
MAX_GIT_OUTPUT = 512 * 1024 * 1024


class CandidatePlanError(RuntimeError):
    """The candidate cannot produce one complete, immutable payload plan."""


def _git(
    repo_root: Path,
    *args: str,
    allow_nonzero: bool = False,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    for variable in tuple(env):
        if variable.startswith("GIT_CONFIG_") and variable != "GIT_CONFIG_NOSYSTEM":
            env.pop(variable, None)
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
        env=env,
    )
    if len(completed.stdout) > MAX_GIT_OUTPUT:
        raise CandidatePlanError("Git object output exceeds the 512 MiB bound")
    if completed.returncode and not allow_nonzero:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CandidatePlanError(
            f"git {' '.join(args)} failed with exit {completed.returncode}: {detail}"
        )
    return completed


def _require_sha(value: str, label: str) -> str:
    result = str(value or "")
    if SHA_RE.fullmatch(result) is None:
        raise CandidatePlanError(
            f"{label} must be an exact lowercase 40-character Git SHA"
        )
    return result


def _safe_repo_path(value: str, label: str) -> str:
    raw = str(value or "")
    if not raw or raw.startswith(("/", "\\")) or "\\" in raw or ":" in raw:
        raise CandidatePlanError(f"{label} is not a canonical repository path: {raw!r}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw):
        raise CandidatePlanError(f"{label} contains a control character: {raw!r}")
    components = raw.split("/")
    if any(
        not component or component in {".", ".."} or component.endswith((".", " "))
        for component in components
    ):
        raise CandidatePlanError(f"{label} is not canonical: {raw!r}")
    return raw


def _safe_copy_source(value: str) -> str:
    """Validate a canonical COPY source while preserving a directory suffix."""
    raw = str(value or "")
    directory_source = raw.endswith("/")
    canonical = raw[:-1] if directory_source else raw
    _safe_repo_path(canonical, "COPY source")
    return raw


def _resolve_commit(repo_root: Path, value: str, label: str) -> str:
    requested = _require_sha(value, label)
    resolved = _git(repo_root, "rev-parse", "--verify", f"{requested}^{{commit}}")
    try:
        actual = resolved.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CandidatePlanError(f"{label} did not resolve to ASCII") from exc
    if actual != requested:
        raise CandidatePlanError(
            f"{label} did not resolve exactly: requested={requested} actual={actual!r}"
        )
    return requested


def _require_ancestry(repo_root: Path, baseline: str, candidate: str) -> None:
    result = _git(
        repo_root,
        "merge-base",
        "--is-ancestor",
        baseline,
        candidate,
        allow_nonzero=True,
    )
    if result.returncode == 1:
        raise CandidatePlanError(
            f"candidate baseline is not an ancestor: {baseline}...{candidate}"
        )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise CandidatePlanError(f"cannot prove candidate ancestry: {detail}")


def _tree(repo_root: Path, revision: str) -> dict[str, dict[str, str]]:
    raw = _git(repo_root, "ls-tree", "-r", "-z", "--full-tree", revision).stdout
    if not raw:
        raise CandidatePlanError(f"exact Git tree is empty: {revision}")
    entries: dict[str, dict[str, str]] = {}
    records = raw.split(b"\0")
    if records[-1] != b"":
        raise CandidatePlanError("Git tree output is not NUL terminated")
    for record in records[:-1]:
        try:
            metadata, encoded_path = record.split(b"\t", 1)
        except ValueError as exc:
            raise CandidatePlanError("malformed Git tree record") from exc
        match = TREE_META_RE.fullmatch(metadata)
        if match is None:
            raise CandidatePlanError(f"unsupported Git tree metadata: {metadata!r}")
        try:
            path = encoded_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidatePlanError("Git tree contains a non-UTF-8 path") from exc
        _safe_repo_path(path, "Git tree path")
        if path in entries:
            raise CandidatePlanError(f"duplicate Git tree path: {path!r}")
        entries[path] = {
            "mode": match.group(1).decode("ascii"),
            "type": match.group(2).decode("ascii"),
            "oid": match.group(3).decode("ascii"),
        }
    return entries


def _require_regular_blob(entry: dict[str, str], path: str) -> None:
    if entry["type"] != "blob" or entry["mode"] not in SAFE_BLOB_MODES:
        raise CandidatePlanError(
            f"managed path must be a regular Git blob: {path!r} "
            f"mode={entry['mode']} type={entry['type']}"
        )


def _blob(repo_root: Path, entry: dict[str, str], path: str) -> bytes:
    _require_regular_blob(entry, path)
    data = _git(repo_root, "cat-file", "blob", entry["oid"]).stdout
    if publisher.git_blob_sha1(data) != entry["oid"]:
        raise CandidatePlanError(f"Git blob identity mismatch: {path!r}")
    return data


def _worktree_head(repo_root: Path) -> str:
    completed = _git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    try:
        return completed.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CandidatePlanError("candidate worktree HEAD is not ASCII") from exc


def _require_worktree_blob(
    repo_root: Path,
    source_path: str,
    expected_oid: str,
) -> None:
    rel = _safe_repo_path(source_path, "publisher source path")
    root = repo_root.resolve(strict=True)
    current = root
    for component in rel.split("/"):
        current = current / component
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise CandidatePlanError(
                f"publisher source is absent from the candidate checkout: {rel!r}"
            ) from exc
        reparse = bool(
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse:
            raise CandidatePlanError(
                f"publisher source traverses a link or reparse point: {rel!r}"
            )
    if not stat.S_ISREG(metadata.st_mode):
        raise CandidatePlanError(
            f"publisher source is not a regular checkout file: {rel!r}"
        )
    try:
        contained = os.path.commonpath(
            (str(root), str(current.resolve(strict=True)))
        ) == str(root)
    except (OSError, ValueError) as exc:
        raise CandidatePlanError(
            f"publisher source cannot be resolved safely: {rel!r}"
        ) from exc
    if not contained:
        raise CandidatePlanError(f"publisher source escapes the checkout: {rel!r}")
    try:
        raw = current.read_bytes()
    except OSError as exc:
        raise CandidatePlanError(
            f"publisher source cannot be read from the checkout: {rel!r}"
        ) from exc
    actual_oid = publisher.git_blob_sha1(raw)
    if actual_oid != expected_oid:
        raise CandidatePlanError(
            "candidate checkout bytes differ from the exact Git object that the "
            f"plan binds: {rel!r} expected={expected_oid} actual={actual_oid}"
        )


TRANSFORM_ATTRIBUTES = (
    "text",
    "eol",
    "crlf",
    "ident",
    "filter",
    "working-tree-encoding",
)


def _transform_attributes(
    repo_root: Path,
    revision: str,
    paths: set[str],
) -> dict[str, tuple[tuple[str, str], ...]]:
    if not paths:
        return {}
    ordered_paths = sorted(paths)
    encoded_paths = b"".join(path.encode("utf-8") + b"\0" for path in ordered_paths)
    raw = _git(
        repo_root,
        "check-attr",
        f"--source={revision}",
        "-z",
        "--stdin",
        *TRANSFORM_ATTRIBUTES,
        input_bytes=encoded_paths,
    ).stdout
    fields = raw.split(b"\0")
    if not fields or fields[-1] != b"":
        raise CandidatePlanError("git check-attr output is not NUL terminated")
    fields = fields[:-1]
    if len(fields) % 3:
        raise CandidatePlanError("git check-attr returned a malformed record set")
    observed: dict[str, list[tuple[str, str]]] = {path: [] for path in ordered_paths}
    for index in range(0, len(fields), 3):
        try:
            path = fields[index].decode("utf-8")
            attribute = fields[index + 1].decode("ascii")
            value = fields[index + 2].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidatePlanError(
                "git check-attr returned non-canonical text"
            ) from exc
        if path not in observed or attribute not in TRANSFORM_ATTRIBUTES:
            raise CandidatePlanError(
                "git check-attr returned an unexpected path or attribute"
            )
        observed[path].append((attribute, value))
    expected_count = len(TRANSFORM_ATTRIBUTES)
    if any(len(values) != expected_count for values in observed.values()):
        raise CandidatePlanError("git check-attr returned an incomplete attribute set")
    return {path: tuple(values) for path, values in observed.items()}



def _strict_copy_sources(dockerfile: str) -> list[str]:
    if dockerfile.startswith("\ufeff"):
        raise CandidatePlanError("Dockerfile UTF-8 BOM is forbidden")
    for raw in dockerfile.splitlines():
        stripped = raw.lstrip()
        if stripped.lower().startswith("# escape="):
            raise CandidatePlanError(
                "candidate planner forbids Dockerfile escape directives"
            )
        if not stripped.startswith("#") and "`" in raw:
            raise CandidatePlanError(
                "candidate planner forbids backtick Dockerfile syntax"
            )
    logical: list[str] = []
    pending = ""
    for raw in dockerfile.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        logical.append(pending + line)
        pending = ""
    if pending:
        raise CandidatePlanError("Dockerfile has an unterminated line continuation")

    canonical_sources: list[str] = []
    for line in logical:
        match = re.match(r"^\s*(COPY|ADD)\s+(.*)$", line, re.IGNORECASE)
        if match is None:
            continue
        instruction, rest = match.groups()
        instruction = instruction.upper()
        rest = rest.strip()

        if instruction == "ADD":
            if rest.startswith("["):
                raise CandidatePlanError("candidate planner forbids JSON-form ADD")
            if "<<" in rest:
                raise CandidatePlanError(
                    "candidate planner forbids ADD heredoc syntax"
                )
            if any(character in rest for character in ('"', "'", "\\", "$", "#")):
                raise CandidatePlanError(
                    f"candidate planner forbids ambiguous ADD syntax: {line.strip()}"
                )
            tokens = rest.split()
            flags = [token for token in tokens if token.startswith("--")]
            clean = [token for token in tokens if not token.startswith("--")]
            if len(clean) != 2 or not publisher.is_remote_add_source(clean[0]):
                raise CandidatePlanError(
                    "candidate planner forbids local or ambiguous ADD instructions"
                )
            if not clean[0].lower().startswith(("http://", "https://")):
                raise CandidatePlanError(
                    "candidate planner supports only checksum-pinned HTTP(S) remote ADD"
                )
            checksum_pattern = r"--checksum=sha256:[0-9a-f]{64}"
            if len(flags) != 1 or re.fullmatch(checksum_pattern, flags[0]) is None:
                raise CandidatePlanError(
                    "candidate planner requires one lowercase SHA-256 checksum for remote ADD"
                )
            continue

        if rest.startswith("["):
            raise CandidatePlanError("candidate planner forbids JSON-form COPY")
        if rest.startswith("--"):
            raise CandidatePlanError("candidate planner forbids COPY flags")
        if "<<" in rest:
            raise CandidatePlanError("candidate planner forbids COPY heredoc syntax")
        if any(character in rest for character in ('"', "'", "\\", "$", "#")):
            raise CandidatePlanError(
                f"candidate planner forbids ambiguous COPY syntax: {line.strip()}"
            )
        tokens = rest.split()
        if len(tokens) < 2:
            raise CandidatePlanError(
                f"COPY has no complete source/destination pair: {line.strip()}"
            )
        for source in tokens[:-1]:
            if any(character in source for character in "*?["):
                raise CandidatePlanError(
                    f"candidate planner forbids glob COPY sources: {source!r}"
                )
            canonical_sources.append(_safe_copy_source(source))

    try:
        publisher_sources = publisher.parse_copy_sources(dockerfile)
    except (publisher.DeployContractError, ValueError, json.JSONDecodeError) as exc:
        raise CandidatePlanError(
            f"production publisher rejected Dockerfile: {exc}"
        ) from exc
    if publisher_sources != list(dict.fromkeys(canonical_sources)):
        raise CandidatePlanError(
            "candidate planner and production publisher derived different COPY sources"
        )
    if not publisher_sources:
        raise CandidatePlanError("Dockerfile has no supported COPY sources")
    return publisher_sources

def _ignore_patterns(data: bytes) -> list[tuple[bool, re.Pattern[str]]]:
    with tempfile.TemporaryDirectory(prefix="szl-hf-plan-ignore-") as directory:
        path = Path(directory) / "Dockerfile.dockerignore"
        path.write_bytes(data)
        try:
            return publisher._dockerignore_patterns(str(path))
        except (publisher.DeployContractError, OSError, ValueError) as exc:
            raise CandidatePlanError(f"invalid Docker ignore contract: {exc}") from exc


def _is_ignored(path: str, patterns: list[tuple[bool, re.Pattern[str]]]) -> bool:
    parents = path.split("/")[:-1]
    candidates = [path] + [
        "/".join(parents[: index + 1]) for index in range(len(parents))
    ]
    ignored = {candidate: False for candidate in candidates}
    for negated, pattern in patterns:
        for candidate in candidates:
            if pattern.fullmatch(candidate):
                ignored[candidate] = not negated
    return any(ignored.values())


def _snapshot(
    repo_root: Path,
    revision: str,
    *,
    dockerfile_path: str,
    include_readme: bool,
    readme_path: str,
) -> dict[str, Any]:
    entries = _tree(repo_root, revision)
    dockerfile_path = _safe_repo_path(dockerfile_path, "Dockerfile path")
    readme_path = publisher.validate_readme_target(readme_path, include_readme)
    dockerfile_entry = entries.get(dockerfile_path)
    if dockerfile_entry is None:
        raise CandidatePlanError(
            f"Dockerfile is absent at {revision}: {dockerfile_path}"
        )
    dockerfile_bytes = _blob(repo_root, dockerfile_entry, dockerfile_path)
    try:
        dockerfile = dockerfile_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidatePlanError("Dockerfile is not strict UTF-8") from exc
    sources = _strict_copy_sources(dockerfile)

    object_ids = {path: entry["oid"] for path, entry in entries.items()}
    targets, unresolved = publisher.expand_sources(sources, object_ids)
    if unresolved:
        raise CandidatePlanError(
            "Dockerfile COPY sources are unresolved: " + ", ".join(sorted(unresolved))
        )

    ignore_path = next(
        (
            path
            for path in (f"{dockerfile_path}.dockerignore", ".dockerignore")
            if path in entries
        ),
        None,
    )
    patterns: list[tuple[bool, re.Pattern[str]]] = []
    ignore_bytes = b""
    if ignore_path:
        ignore_bytes = _blob(repo_root, entries[ignore_path], ignore_path)
        patterns = _ignore_patterns(ignore_bytes)

    files: dict[str, dict[str, Any]] = {}
    source_files: dict[str, str] = {}
    ignored_paths: list[str] = []
    for path, copy_source in sorted(targets.items()):
        _safe_repo_path(path, "managed COPY path")
        ignored = bool(patterns and _is_ignored(path, patterns))
        if ignored:
            ignored_paths.append(path)
        entry = entries[path]
        _require_regular_blob(entry, path)
        source_files[path] = entry["oid"]
        files[path] = {
            "mode": entry["mode"],
            "oid": entry["oid"],
            "copy_source": copy_source,
            "docker_context_included": not ignored,
        }

    # include-readme is authoritative in the production publisher. It replaces
    # any same-path Dockerfile-derived entry with the Space-card mapping.
    if not include_readme:
        files.pop(readme_path, None)
        source_files.pop(readme_path, None)

    files["Dockerfile"] = {
        "mode": dockerfile_entry["mode"],
        "oid": dockerfile_entry["oid"],
        "copy_source": "(dockerfile)",
        "source_path": dockerfile_path,
        "docker_context_included": None,
    }
    source_files[dockerfile_path] = dockerfile_entry["oid"]
    if include_readme:
        readme_entry = entries.get(readme_path)
        if readme_entry is None:
            raise CandidatePlanError(f"included README is absent: {readme_path!r}")
        _blob(repo_root, readme_entry, readme_path)
        source_files[readme_path] = readme_entry["oid"]
        files[readme_path] = {
            "mode": readme_entry["mode"],
            "oid": readme_entry["oid"],
            "copy_source": "(readme)",
            "docker_context_included": None,
        }
    deployed_ignore_oid = publisher.git_blob_sha1(ignore_bytes)
    files["Dockerfile.dockerignore"] = {
        "mode": entries[ignore_path]["mode"] if ignore_path else "100644",
        "oid": deployed_ignore_oid,
        "copy_source": "(dockerignore-control)",
        "source_path": ignore_path or "(generated-empty-dockerignore)",
        "docker_context_included": None,
    }
    if ignore_path:
        source_files[ignore_path] = entries[ignore_path]["oid"]
    if not files:
        raise CandidatePlanError("candidate payload set is empty")
    return {
        "revision": revision,
        "dockerfile_path": dockerfile_path,
        "effective_dockerignore": ignore_path,
        "copy_sources": sorted(sources),
        "unresolved_sources": [],
        "docker_context_ignored_paths": ignored_paths,
        "managed_count": len(files),
        "source_files": dict(sorted(source_files.items())),
        "files": files,
    }


def build_plan(
    repo_root: Path,
    github_repo: str,
    baseline_ref: str,
    candidate_ref: str,
    *,
    dockerfile_path: str = "Dockerfile",
    include_readme: bool = True,
    readme_path: str = "README.md",
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    if not (root / ".git").exists():
        raise CandidatePlanError(f"repo-root is not a Git worktree: {root}")
    if REPOSITORY_RE.fullmatch(str(github_repo or "")) is None:
        raise CandidatePlanError(
            "github-repo must be one canonical owner/repository identifier"
        )
    baseline = _resolve_commit(root, baseline_ref, "candidate baseline")
    candidate = _resolve_commit(root, candidate_ref, "candidate head")
    _require_ancestry(root, baseline, candidate)
    observed_head = _worktree_head(root)
    if observed_head != candidate:
        raise CandidatePlanError(
            "candidate checkout HEAD is not the exact requested candidate: "
            f"expected={candidate} actual={observed_head}"
        )
    before = _snapshot(
        root,
        baseline,
        dockerfile_path=dockerfile_path,
        include_readme=include_readme,
        readme_path=readme_path,
    )
    after = _snapshot(
        root,
        candidate,
        dockerfile_path=dockerfile_path,
        include_readme=include_readme,
        readme_path=readme_path,
    )

    for source_path, expected_oid in after["source_files"].items():
        _require_worktree_blob(root, source_path, expected_oid)

    common_sources = set(before["source_files"]) & set(after["source_files"])
    baseline_attributes = _transform_attributes(root, baseline, common_sources)
    candidate_attributes = _transform_attributes(root, candidate, common_sources)
    changed_attributes = sorted(
        path
        for path in common_sources
        if baseline_attributes[path] != candidate_attributes[path]
    )
    if changed_attributes:
        raise CandidatePlanError(
            "candidate changes checkout-transform attributes for publisher source "
            "paths: " + ", ".join(changed_attributes)
        )

    baseline_files = before["files"]
    candidate_files = after["files"]
    removed_managed_paths = sorted(set(baseline_files) - set(candidate_files))
    if removed_managed_paths:
        raise CandidatePlanError(
            "candidate removes managed payload paths; remote prune authority is "
            "not proven by this admission plan: " + ", ".join(removed_managed_paths)
        )

    newly_ignored = sorted(
        set(after["docker_context_ignored_paths"])
        - set(before["docker_context_ignored_paths"])
    )
    if newly_ignored:
        raise CandidatePlanError(
            "candidate newly excludes managed COPY paths from the Docker context: "
            + ", ".join(newly_ignored)
        )

    deltas: list[dict[str, Any]] = []
    all_paths = sorted(set(baseline_files) | set(candidate_files))
    for path in all_paths:
        old = before["files"].get(path)
        new = after["files"].get(path)
        if old == new:
            continue
        if old is None:
            kind = "managed-added"
        elif new is None:
            kind = "managed-removed"
        else:
            kind = "modified"
        deltas.append(
            {
                "path": path,
                "kind": kind,
                "baseline_blob_sha": old["oid"] if old else None,
                "candidate_blob_sha": new["oid"] if new else None,
                "baseline_mode": old["mode"] if old else None,
                "candidate_mode": new["mode"] if new else None,
                "baseline_copy_source": old["copy_source"] if old else None,
                "candidate_copy_source": new["copy_source"] if new else None,
                "baseline_docker_context_included": (
                    old["docker_context_included"] if old else None
                ),
                "candidate_docker_context_included": (
                    new["docker_context_included"] if new else None
                ),
                "baseline_managed": old is not None,
                "candidate_managed": new is not None,
            }
        )

    plan: dict[str, Any] = {
        "schema": 1,
        "mode": "candidate-managed-plan",
        "status": "changes" if deltas else "no-changes",
        "github_repo": github_repo,
        "baseline_ref": baseline,
        "candidate_ref": candidate,
        "dockerfile_path": dockerfile_path,
        "include_readme": include_readme,
        "readme_path": readme_path if include_readme else None,
        "network_requests": 0,
        "allowlist_used": False,
        "error_count": 0,
        "baseline": before,
        "candidate": after,
        "delta_count": len(deltas),
        "deltas": deltas,
    }
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan


def _invalid_report(args: argparse.Namespace, detail: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": 1,
        "mode": "candidate-managed-plan",
        "status": "invalid",
        "github_repo": args.github_repo,
        "baseline_ref": args.trusted_base_ref,
        "candidate_ref": args.candidate_ref,
        "network_requests": 0,
        "allowlist_used": False,
        "error_count": 1,
        "findings": [
            {
                "path": "(candidate-plan)",
                "kind": "candidate-plan-contract-error",
                "severity": "error",
                "detail": detail,
            }
        ],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["canonical_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--github-repo", required=True)
    parser.add_argument("--trusted-base-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument("--dockerfile-path", default="Dockerfile")
    parser.add_argument("--include-readme", choices=("true", "false"), default="true")
    parser.add_argument("--readme-path", default="README.md")
    parser.add_argument("--report-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = build_plan(
            args.repo_root,
            args.github_repo,
            args.trusted_base_ref,
            args.candidate_ref,
            dockerfile_path=args.dockerfile_path,
            include_readme=args.include_readme == "true",
            readme_path=args.readme_path,
        )
    except (
        CandidatePlanError,
        publisher.DeployContractError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        report = _invalid_report(args, str(exc))
        args.report_out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"::error title=HF candidate plan::{exc}", file=sys.stderr)
        return 1

    args.report_out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "HF candidate plan exact: "
        f"{report['baseline_ref']} -> {report['candidate_ref']} "
        f"managed={report['candidate']['managed_count']} "
        f"deltas={report['delta_count']} "
        f"sha256={report['canonical_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
