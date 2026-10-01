#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only, bounded projection of canonical policy and visible public source."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import time

import estate_alignment_contract as alignment
import router_flagship_contract as router

ORG = "szl-holdings"
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_BYTES = 8_000_000
QUERY = """query($cursor:String){organization(login:"szl-holdings"){
repositories(first:100,after:$cursor,privacy:PUBLIC,orderBy:{field:NAME,direction:ASC}){
totalCount pageInfo{hasNextPage endCursor} nodes{id name isPrivate isArchived
description pushedAt licenseInfo{spdxId} defaultBranchRef{name target{... on Commit{
oid tree{oid entries{name type}} statusCheckRollup{state}}}}}}}}"""
AUTHORITIES = ("docs/ESTATE_ALIGNMENT_CONTRACT_V1.json",
               "governance/archive-portfolio-v2.json", "governance/router-flagship-v1.json")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class ObservationError(RuntimeError):
    """Fixed diagnostics only: never serialize CLI stderr or provider bodies."""


class GitHubGraphQL:
    def __init__(self):
        self.started, self.calls, self.responses = time.monotonic(), 0, []

    def __call__(self, query, variables=None):
        if not re.match(r"^\s*query\b", query):
            raise ObservationError("READ_ONLY_QUERY_REQUIRED")
        if self.calls >= 30 or time.monotonic() - self.started > 240:
            raise ObservationError("OBSERVATION_BUDGET_EXCEEDED")
        self.calls += 1
        try:
            # gh retains its existing credential in its normal authentication path.
            # Explicit hostname prevents GH_HOST from redirecting the observation.
            result = subprocess.run(
                ["gh", "api", "--hostname", "github.com", "graphql", "--input", "-"],
                input=encoded({"query": query, "variables": variables or {}}),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=40,
            )
            if not result.stdout or len(result.stdout) > MAX_BYTES:
                raise ObservationError("GRAPHQL_BODY_UNAVAILABLE_OR_OVERSIZE")
            value = alignment.load_json_bytes(result.stdout, label="GraphQL response")
        except (OSError, subprocess.TimeoutExpired, alignment.AlignmentError):
            raise ObservationError("GRAPHQL_READ_UNAVAILABLE") from None
        self.responses.append({"observed_at": now(), "sha256": digest(result.stdout),
                               "bytes": len(result.stdout), "exit_code": result.returncode})
        if result.returncode and not value.get("errors"):
            raise ObservationError("GRAPHQL_CLI_FAILED")
        return value


def census(request):
    rows, cursors, failures, cursor, expected = {}, set(), [], None, None
    for _ in range(20):
        try:
            response = request(QUERY, {"cursor": cursor})
            connection = response["data"]["organization"]["repositories"]
            count, nodes, page = connection["totalCount"], connection["nodes"], connection["pageInfo"]
            if type(count) is not int or not 0 <= count <= 2000 or not isinstance(nodes, list):
                raise ObservationError("CENSUS_SCHEMA")
            if expected is not None and count != expected:
                raise ObservationError("CENSUS_COUNT_MOVED")
            expected = count
            for row in nodes:
                name = row.get("name", "") if isinstance(row, dict) else ""
                if not NAME.fullmatch(name) or name in (".", "..") or row.get("isPrivate") is not False:
                    raise ObservationError("CENSUS_PUBLIC_IDENTITY")
                if type(row.get("isArchived")) is not bool or not isinstance(row.get("id"), str):
                    raise ObservationError("CENSUS_REPOSITORY_SCHEMA")
                if name in rows or any(other["id"] == row["id"] for other in rows.values()):
                    raise ObservationError("CENSUS_DUPLICATE")
                rows[name] = row
            if response.get("errors"):
                raise ObservationError("GRAPHQL_PARTIAL_DATA")
            if type(page.get("hasNextPage")) is not bool or len(nodes) > 100:
                raise ObservationError("CENSUS_PAGE_SCHEMA")
            if not page["hasNextPage"]:
                if len(rows) != expected:
                    raise ObservationError("CENSUS_CARDINALITY")
                return rows, {"state": "OBSERVED", "reported_visible_count": expected, "failures": []}
            cursor = page.get("endCursor")
            if not isinstance(cursor, str) or not cursor or cursor in cursors or len(nodes) != 100:
                raise ObservationError("CENSUS_CURSOR")
            cursors.add(cursor)
        except (KeyError, TypeError, AttributeError):
            failures.append("CENSUS_SCHEMA")
            break
        except ObservationError as exc:
            failures.append(str(exc))
            break
    else:
        failures.append("CENSUS_PAGE_BUDGET")
    return rows, {"state": "PARTIAL", "reported_visible_count": expected, "failures": failures}


def documents(entries):
    if not isinstance(entries, list):
        raise ObservationError("TREE_ENTRIES_UNAVAILABLE")
    if any(not isinstance(row, dict) or not isinstance(row.get("name"), str)
           or row.get("type") not in ("blob", "tree", "commit") for row in entries):
        raise ObservationError("TREE_ENTRIES_SCHEMA")
    files = {row["name"].casefold() for row in entries if row["type"] == "blob"}
    return {"README": any(re.fullmatch(r"readme(?:\.[a-z0-9]+)?", name) for name in files),
            "LICENSE": any(re.fullmatch(r"(?:license|licence|copying)(?:\.[a-z0-9-]+)?", name) for name in files),
            "SECURITY": any(re.fullmatch(r"security(?:\.[a-z0-9]+)?", name) for name in files)}


def project(rows):
    output = []
    for name, raw in sorted(rows.items()):
        license_info = raw.get("licenseInfo")
        license_id = license_info.get("spdxId") if isinstance(license_info, dict) else None
        item = {"repository": f"{ORG}/{name}", "archived": raw["isArchived"],
                "description_present": bool(raw.get("description")),
                "license": license_id if isinstance(license_id, str) and re.fullmatch(r"[A-Za-z0-9.+-]{1,80}", license_id) else "UNKNOWN",
                "pushed_at": raw.get("pushedAt"), "readiness": "NOT_OBSERVED",
                "head_sha": None, "tree_sha": None, "head_state": "UNKNOWN",
                "documents": {key: "UNKNOWN" for key in ("README", "LICENSE", "SECURITY")},
                "ci": {"state": "UNKNOWN", "required_checks_known": False}, "failures": []}
        if raw["isArchived"]:
            item["head_state"] = "NOT_REQUESTED_ARCHIVED"
        else:
            try:
                branch = raw["defaultBranchRef"]
                target = branch["target"]
                if not SHA.fullmatch(target["oid"]) or not SHA.fullmatch(target["tree"]["oid"]):
                    raise ObservationError("HEAD_IDENTITY")
                item.update(head_sha=target["oid"],
                            tree_sha=target["tree"]["oid"], head_state="OBSERVED")
                item["documents"] = {key: "PRESENT" if value else "ABSENT"
                                     for key, value in documents(target["tree"]["entries"]).items()}
                raw_rollup = target.get("statusCheckRollup")
                if raw_rollup is not None and not isinstance(raw_rollup, dict):
                    raise ObservationError("CI_ROLLUP_SCHEMA")
                rollup = (raw_rollup or {}).get("state")
                if rollup in ("SUCCESS", "FAILURE", "PENDING", "ERROR", "EXPECTED"):
                    item["ci"]["state"] = rollup
                item["ci"]["scope"] = "EXACT_HEAD_STATUS_CHECK_ROLLUP_ONLY"
            except (KeyError, TypeError, AttributeError, ObservationError):
                item["failures"].append("HEAD_OR_TREE_UNAVAILABLE")
        output.append(item)
    return output


def recheck(request, repositories):
    active = [row for row in repositories if not row["archived"] and row["head_sha"]]
    for start in range(0, len(active), 25):
        batch = active[start:start + 25]
        parts = []
        for index, row in enumerate(batch):
            name = row["repository"].split("/")[1]
            parts.append(f'r{index}:repository(owner:"{ORG}",name:"{name}"){{'
                         f'object(expression:"{row["head_sha"]}:.github"){{... on Tree{{entries{{name type}}}}}}'
                         'defaultBranchRef{target{... on Commit{oid}}}}')
        try:
            response = request("query{" + " ".join(parts) + "}")
            if response.get("errors"):
                raise ObservationError("GRAPHQL_PARTIAL_RECHECK")
            for index, row in enumerate(batch):
                value = response["data"][f"r{index}"]
                if value["defaultBranchRef"]["target"]["oid"] != row["head_sha"]:
                    row["head_state"] = "MOVED"
                    row["failures"].append("DEFAULT_HEAD_MOVED")
                else:
                    row["head_state"] = "REOBSERVED_SAME"
                github = value.get("object")
                if github and documents(github["entries"])["SECURITY"]:
                    row["documents"]["SECURITY"] = "PRESENT"
        except (KeyError, TypeError, AttributeError, ObservationError):
            for row in batch:
                row["head_state"] = "UNKNOWN_RECHECK"
                row["failures"].append("HEAD_RECHECK_UNAVAILABLE")
                if row["documents"]["SECURITY"] == "ABSENT":
                    row["documents"]["SECURITY"] = "UNKNOWN"


def snapshot_delta(path, observed_at, repositories, complete):
    if not observed_at or dt.datetime.fromisoformat(observed_at.replace("Z", "+00:00")).tzinfo is None:
        raise ObservationError("SNAPSHOT_OBSERVATION_TIME_REQUIRED")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ObservationError("SNAPSHOT_OVERSIZE")
    old = {}
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or not {"repo", "archived"}.issubset(reader.fieldnames) or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ObservationError("SNAPSHOT_COLUMNS")
    for row in reader:
        name = row.get("repo", "")
        if not NAME.fullmatch(name) or name in (".", "..") or name in old or row.get("archived") not in ("True", "False"):
            raise ObservationError("SNAPSHOT_SCHEMA_OR_DUPLICATE")
        old[name] = row["archived"] == "True"
        if len(old) > 2000:
            raise ObservationError("SNAPSHOT_REPOSITORY_BUDGET")
    if not old:
        raise ObservationError("SNAPSHOT_EMPTY")
    current = {row["repository"].split("/")[1]: row["archived"] for row in repositories}
    return {"trust": "UNSIGNED_INPUT_CONTEXT", "sha256": digest(raw), "observed_at": observed_at,
            "added_visible": sorted(current.keys() - old.keys()),
            "not_observed": sorted(old.keys() - current.keys()) if complete else "UNKNOWN_PARTIAL_CENSUS",
            "archived_state_changed": sorted(name for name in old.keys() & current.keys() if old[name] != current[name]),
            "claim_boundary": "Visibility deltas do not prove repository creation, deletion, or operational change."}


def validation_projection(value, key, success, failure_code):
    status = value.get(key) if isinstance(value, dict) else None
    failures = value.get("failures", []) if isinstance(value, dict) else []
    return {key: success if status == success and failures == [] else "UNKNOWN_OR_FAILED",
            "result_sha256": digest(encoded(value)),
            "failure_count": len(failures) if isinstance(failures, list) else None,
            "failures": [] if status == success and failures == [] else [failure_code]}


def branch_oid(row):
    branch = row.get("defaultBranchRef") if isinstance(row, dict) else None
    target = branch.get("target") if isinstance(branch, dict) else None
    return target.get("oid") if isinstance(target, dict) else None


def collect(root, request, snapshot=None, observed_at=None):
    receipt = {"schema": "szl.estate-operational-observation/v1", "started_at": now(),
               "trust": "UNSIGNED_HONEST", "scope": "AUTHENTICATED_VISIBLE_PUBLIC",
               "organization_complete": False, "provider_writes": False, "readiness": "NOT_OBSERVED",
               "collector_sha256": digest(Path(__file__).read_bytes()), "authority_files": {}, "failures": []}
    receipt["validator_sources"] = {
        ".github/scripts/estate_alignment_contract.py": digest(Path(alignment.__file__).read_bytes()),
        ".github/scripts/router_flagship_contract.py": digest(Path(router.__file__).read_bytes())}
    for relative in AUTHORITIES:
        receipt["authority_files"][relative] = digest((root / relative).read_bytes())
    contract = alignment.load_json(root / AUTHORITIES[0])
    archive = alignment.load_json(root / AUTHORITIES[1])
    if archive.get("schema") != "szl.archive-portfolio/v2" or not isinstance(archive.get("repositories"), list):
        raise ObservationError("ARCHIVE_AUTHORITY_SCHEMA")
    if any(not isinstance(row, dict) or not NAME.fullmatch(str(row.get("name", "")))
           or row.get("disposition") not in ("restore", "consolidate", "historical") for row in archive["repositories"]):
        raise ObservationError("ARCHIVE_AUTHORITY_SCHEMA")
    alignment_result = alignment.build_receipt(root, live=False)
    revision = alignment_result.get("source_revision")
    receipt["canonical_checkout_revision"] = revision if isinstance(revision, str) and SHA.fullmatch(revision) else "UNKNOWN"
    receipt["canonical_validation"] = {
        "alignment": validation_projection(alignment_result, "state", "ALIGNED", "ALIGNMENT_VALIDATION_FAILED"),
        "router": validation_projection(router.validate(root), "status", "PASS", "ROUTER_VALIDATION_FAILED")}
    rows, coverage = census(request)
    receipt["coverage"] = coverage
    repositories = project(rows)
    recheck(request, repositories)
    policy_sources = alignment.canonical_repositories(contract) | {router.SOURCE}
    dispositions = {row["name"]: row["disposition"] for row in archive["repositories"]}
    for row in repositories:
        row["canonical_source_declared"] = row["repository"] in policy_sources
        row["historical_archive_disposition"] = dispositions.get(row["repository"].split("/")[1], "UNKNOWN")
    receipt["repositories"] = repositories
    if coverage["state"] == "OBSERVED":
        final_rows, final_coverage = census(request)
        if final_coverage["state"] != "OBSERVED" or {k: v["id"] for k, v in rows.items()} != {k: v["id"] for k, v in final_rows.items()}:
            receipt["failures"].append("VISIBLE_MEMBERSHIP_CHANGED_OR_UNAVAILABLE")
        for row in repositories:
            name = row["repository"].split("/")[1]
            final = final_rows.get(name)
            if not final or final["id"] != rows[name]["id"]:
                row["head_state"] = "UNKNOWN_FINAL_CENSUS"
                row["failures"].append("FINAL_REPOSITORY_IDENTITY_UNAVAILABLE")
            elif final["isArchived"] != rows[name]["isArchived"]:
                row["head_state"] = "STATE_CHANGED"
                row["failures"].append("ARCHIVED_STATE_CHANGED_FINAL_CENSUS")
            elif branch_oid(final) != branch_oid(rows[name]):
                row["head_state"] = "MOVED"
                row["failures"].append("DEFAULT_HEAD_MOVED_FINAL_CENSUS")
        receipt["coverage"]["final_recheck"] = final_coverage
    if snapshot:
        try:
            receipt["snapshot_comparison"] = snapshot_delta(snapshot, observed_at, repositories,
                                                            coverage["state"] == "OBSERVED" and not receipt["failures"])
        except (OSError, ValueError, UnicodeError, ObservationError):
            receipt["failures"].append("SNAPSHOT_UNAVAILABLE_OR_INVALID")
    local = receipt["canonical_validation"]
    partial = (coverage["state"] != "OBSERVED" or receipt["failures"] or any(row["failures"] for row in repositories)
               or local["alignment"]["state"] != "ALIGNED" or local["router"]["status"] != "PASS")
    receipt.update(state="PARTIAL" if partial else "OBSERVED", finished_at=now(),
                   claim_boundary="Sequential source observations; no org-completeness, required-CI, merge, publication, deployment, readiness, or signature claim.")
    receipt["response_commitments"] = getattr(request, "responses", [])
    return receipt


def save(receipt, output):
    # Create a new generation atomically; never replace a previous observation.
    output.mkdir(parents=True, exist_ok=False)
    lines = ["# Estate operational observation", "", f'State: **{receipt["state"]}**. Trust: **UNSIGNED_HONEST**.', "",
             f'Observed {len(receipt["repositories"])} visible public repositories. Scope: `{receipt["scope"]}`.', "",
             receipt["claim_boundary"], "", "| Repository | Source head | CI rollup | README / LICENSE / SECURITY |",
             "|---|---|---|---|"]
    for row in receipt["repositories"]:
        docs = " / ".join(row["documents"][key] for key in ("README", "LICENSE", "SECURITY"))
        head = row["head_sha"] or row["head_state"]
        lines.append(f'| {row["repository"]} | {head} ({row["head_state"]}) | {row["ci"]["state"]} | {docs} |')
    lines += ["", "Authority hashes, fixed diagnostics, snapshot deltas, and response commitments are in inventory.json.", ""]
    report = "\n".join(lines).encode()
    receipt["report_sha256"] = digest(report)
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = digest(encoded(receipt))
    (output / "inventory.md").write_bytes(report)
    (output / "inventory.json").write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--snapshot-csv", type=Path)
    parser.add_argument("--snapshot-observed-at")
    args = parser.parse_args()
    if args.output_dir.exists():
        print(json.dumps({"state": "REFUSED", "failure": "OUTPUT_DIRECTORY_ALREADY_EXISTS"}))
        return 2
    try:
        receipt = collect(args.repo_root.resolve(), GitHubGraphQL(), args.snapshot_csv, args.snapshot_observed_at)
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            ObservationError, alignment.AlignmentError, router.ContractError):
        receipt = {"schema": "szl.estate-operational-observation/v1", "state": "PARTIAL",
                   "scope": "AUTHENTICATED_VISIBLE_PUBLIC", "repositories": [],
                   "trust": "UNSIGNED_HONEST", "organization_complete": False,
                   "provider_writes": False, "readiness": "NOT_OBSERVED",
                   "failures": ["CANONICAL_INPUT_UNAVAILABLE_OR_INVALID"],
                   "claim_boundary": "No operational claim is authorized by this incomplete observation."}
    try:
        save(receipt, args.output_dir)
    except OSError:
        print(json.dumps({"state": "REFUSED", "failure": "OUTPUT_DIRECTORY_EXISTS_OR_UNAVAILABLE"}))
        return 2
    print(json.dumps({"state": receipt["state"], "repositories": len(receipt["repositories"]),
                      "receipt_sha256": receipt["receipt_sha256"]}))
    return 0 if receipt["state"] == "OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
