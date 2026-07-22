#!/usr/bin/env python3
"""Immutable issue-evidence validators for active-estate reconciliation v5."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from final_estate_v5_core import (
    CLONE_IDS,
    EVIDENCE_ISSUES,
    INVENTORY_SCHEMAS,
    KERNEL_IDS,
    REPLIT_DECOMMISSION_ISSUE,
    REPLIT_DECOMMISSION_MARKER,
    SHA40,
    SHA64,
    Gate,
    GitHubClient,
    latest_report,
    selfcheck_passed,
    summary_clean,
)

READINESS_SCHEMA = "szl.hf-release-readiness/v1"
PUBLICATION_SCHEMA = "szl.hf-release-finalization/v2"


def validate_official_inventory(report: Mapping[str, Any]) -> tuple[bool, str]:
    counts = report.get("counts") or {}
    canonical = report.get("canonical_a11oy") or {}
    clones = report.get("clone_absence") or {}
    required = (
        "models",
        "datasets",
        "spaces",
        "kernels",
        "collections",
        "collection_references",
        "buckets",
    )
    counts_ok = isinstance(counts, Mapping) and all(
        isinstance(counts.get(key), int) and counts[key] > 0 for key in required
    )
    clones_ok = (
        isinstance(clones, Mapping)
        and set(clones) == CLONE_IDS
        and all(value is True for value in clones.values())
    )
    canonical_ok = (
        isinstance(canonical, Mapping)
        and canonical.get("private") is False
        and str(canonical.get("sdk") or "").lower() == "docker"
        and str(canonical.get("stage") or "").upper() == "RUNNING"
        and SHA40.fullmatch(str(canonical.get("sha") or "")) is not None
        and isinstance(canonical.get("file_count"), int)
        and canonical["file_count"] > 0
    )
    ok = (
        report.get("schema") in INVENTORY_SCHEMAS
        and report.get("publish") is True
        and summary_clean(report)
        and counts_ok
        and canonical_ok
        and clones_ok
    )
    return ok, (
        f"schema={report.get('schema')}; publish={report.get('publish')}; "
        f"summary_clean={summary_clean(report)}; counts_ok={counts_ok}; "
        f"canonical_ok={canonical_ok}; clones_ok={clones_ok}"
    )


def validate_release_readiness(report: Mapping[str, Any]) -> tuple[bool, str]:
    results = report.get("results") or {}
    dataset = results.get("dataset") if isinstance(results, Mapping) else None
    kernels = results.get("kernels") if isinstance(results, Mapping) else None
    dataset_ok = (
        isinstance(dataset, Mapping)
        and dataset.get("viewer_http_status") == 200
        and SHA40.fullmatch(str(dataset.get("revision") or "")) is not None
        and isinstance(dataset.get("remote_file_count"), int)
        and dataset["remote_file_count"] > 0
    )
    kernel_ids = set(kernels) if isinstance(kernels, Mapping) else set()
    kernels_ok = kernel_ids == KERNEL_IDS and all(
        isinstance(kernels[repo_id], Mapping)
        and SHA40.fullmatch(str(kernels[repo_id].get("revision") or "")) is not None
        and isinstance(kernels[repo_id].get("remote_file_count"), int)
        and kernels[repo_id]["remote_file_count"] > 0
        and selfcheck_passed(kernels[repo_id].get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    ok = (
        report.get("schema") == READINESS_SCHEMA
        and report.get("publish") is True
        and summary_clean(report)
        and dataset_ok
        and kernels_ok
    )
    return ok, (
        f"schema={report.get('schema')}; publish={report.get('publish')}; "
        f"summary_clean={summary_clean(report)}; dataset_ok={dataset_ok}; "
        f"kernels_ok={kernels_ok}; kernels={sorted(kernel_ids)}"
    )


def validate_release_publication(report: Mapping[str, Any]) -> tuple[bool, str]:
    runtime = report.get("runtime") or {}
    results = report.get("results") or {}
    dataset = results.get("dataset") if isinstance(results, Mapping) else None
    kernels = results.get("kernels") if isinstance(results, Mapping) else None
    sources = report.get("sources") or {}
    runtime_ok = (
        isinstance(runtime, Mapping)
        and runtime.get("numpy") == "2.2.6"
        and str(runtime.get("torch") or "").startswith("2.7.1")
    )
    dataset_ok = (
        isinstance(dataset, Mapping)
        and dataset.get("viewer_http_status") == 200
        and SHA40.fullmatch(str(dataset.get("revision") or "")) is not None
        and isinstance(dataset.get("remote_file_count"), int)
        and dataset["remote_file_count"] > 0
    )
    kernel_ids = set(kernels) if isinstance(kernels, Mapping) else set()
    kernels_ok = kernel_ids == KERNEL_IDS and all(
        isinstance(kernels[repo_id], Mapping)
        and SHA40.fullmatch(str(kernels[repo_id].get("revision") or "")) is not None
        and kernels[repo_id].get("transport") == "authenticated-kernel-hub-git"
        and kernels[repo_id].get("build_variants_preserved") is True
        and kernels[repo_id].get("card_contract_byte_parity") is True
        and SHA64.fullmatch(str(kernels[repo_id].get("build_tree_sha256") or "")) is not None
        and isinstance(kernels[repo_id].get("remote_file_count"), int)
        and kernels[repo_id]["remote_file_count"] > 0
        and selfcheck_passed(kernels[repo_id].get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    source_keys = {"szl_lake", "szl_energy_attest", "szl_lambda_gate"}
    sources_ok = (
        isinstance(sources, Mapping)
        and set(sources) == source_keys
        and all(SHA40.fullmatch(str(sources[key] or "")) is not None for key in source_keys)
    )
    ok = (
        report.get("schema") == PUBLICATION_SCHEMA
        and report.get("publish") is True
        and report.get("kernel_transport") == "authenticated-kernel-hub-git"
        and summary_clean(report)
        and runtime_ok
        and dataset_ok
        and kernels_ok
        and sources_ok
    )
    return ok, (
        f"schema={report.get('schema')}; publish={report.get('publish')}; "
        f"summary_clean={summary_clean(report)}; runtime_ok={runtime_ok}; "
        f"dataset_ok={dataset_ok}; kernels_ok={kernels_ok}; sources_ok={sources_ok}"
    )


VALIDATORS: dict[str, Callable[[Mapping[str, Any]], tuple[bool, str]]] = {
    "official_hf_inventory": validate_official_inventory,
    "hf_release_readiness": validate_release_readiness,
    "hf_release_publication": validate_release_publication,
}


def evaluate_issue_gate(
    client: GitHubClient, name: str, repo: str, number: int
) -> Gate:
    try:
        issue = client.issue(repo, number)
        report = latest_report(issue)
        valid, detail = VALIDATORS[name](report)
        return Gate(
            name,
            issue.get("state") == "closed" and valid,
            f"issue_state={issue.get('state')}; {detail}",
            {
                "issue_url": issue.get("html_url") or issue.get("url"),
                "issue_state": issue.get("state"),
                "issue_updated_at": issue.get("updated_at"),
                "report_schema": report.get("schema"),
                "report_generated_at": report.get("generated_at"),
                "report_generation": report.get("generation"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(name, False, f"{type(exc).__name__}: {exc}", {})


def evaluate_release_revision_consistency(client: GitHubClient) -> Gate:
    try:
        readiness_issue = client.issue(*EVIDENCE_ISSUES["hf_release_readiness"])
        publication_issue = client.issue(*EVIDENCE_ISSUES["hf_release_publication"])
        readiness = latest_report(readiness_issue)
        publication = latest_report(publication_issue)
        readiness_results = readiness.get("results") or {}
        publication_results = publication.get("results") or {}
        readiness_dataset = readiness_results.get("dataset")
        publication_dataset = publication_results.get("dataset")
        readiness_kernels = readiness_results.get("kernels")
        publication_kernels = publication_results.get("kernels")
        readiness_dataset_revision = (
            str(readiness_dataset.get("revision") or "")
            if isinstance(readiness_dataset, Mapping)
            else ""
        )
        publication_dataset_revision = (
            str(publication_dataset.get("revision") or "")
            if isinstance(publication_dataset, Mapping)
            else ""
        )
        readiness_kernel_revisions = {
            repo_id: str(readiness_kernels[repo_id].get("revision") or "")
            for repo_id in KERNEL_IDS
            if isinstance(readiness_kernels, Mapping)
            and isinstance(readiness_kernels.get(repo_id), Mapping)
        }
        publication_kernel_revisions = {
            repo_id: str(publication_kernels[repo_id].get("revision") or "")
            for repo_id in KERNEL_IDS
            if isinstance(publication_kernels, Mapping)
            and isinstance(publication_kernels.get(repo_id), Mapping)
        }
        dataset_match = (
            SHA40.fullmatch(readiness_dataset_revision) is not None
            and readiness_dataset_revision == publication_dataset_revision
        )
        kernels_match = (
            set(readiness_kernel_revisions) == KERNEL_IDS
            and readiness_kernel_revisions == publication_kernel_revisions
        )
        schemas_current = (
            readiness.get("schema") == READINESS_SCHEMA
            and publication.get("schema") == PUBLICATION_SCHEMA
        )
        issues_closed = (
            readiness_issue.get("state") == "closed"
            and publication_issue.get("state") == "closed"
        )
        return Gate(
            "evidence:hf_release_revision_consistency",
            dataset_match and kernels_match and schemas_current and issues_closed,
            (
                f"issues_closed={issues_closed}; schemas_current={schemas_current}; "
                f"dataset_match={dataset_match}; kernels_match={kernels_match}"
            ),
            {
                "readiness_issue_url": readiness_issue.get("html_url") or readiness_issue.get("url"),
                "publication_issue_url": publication_issue.get("html_url") or publication_issue.get("url"),
                "readiness_schema": readiness.get("schema"),
                "publication_schema": publication.get("schema"),
                "dataset_revision": readiness_dataset_revision,
                "kernel_revisions": readiness_kernel_revisions,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "evidence:hf_release_revision_consistency",
            False,
            f"{type(exc).__name__}: {exc}",
            {},
        )


def evaluate_replit_decommission(client: GitHubClient) -> Gate:
    repo, number = REPLIT_DECOMMISSION_ISSUE
    try:
        issue = client.issue(repo, number)
        marker = f"<!-- {REPLIT_DECOMMISSION_MARKER} -->" in str(issue.get("body") or "")
        closed = issue.get("state") == "closed"
        not_planned = str(issue.get("state_reason") or "").lower() == "not_planned"
        return Gate(
            "scope:replit_unified_control_hub",
            closed and not_planned and marker,
            (
                f"state={issue.get('state')}; state_reason={issue.get('state_reason')}; "
                f"decommission_marker={marker}; operational_claim=false"
            ),
            {
                "issue_url": issue.get("html_url") or issue.get("url"),
                "issue_updated_at": issue.get("updated_at"),
                "decision": "DECOMMISSIONED_NOT_IN_ACTIVE_ESTATE",
                "operational_claim": False,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "scope:replit_unified_control_hub",
            False,
            f"{type(exc).__name__}: {exc}",
            {},
        )
