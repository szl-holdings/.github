#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import frontier_payload as operator  # noqa: E402


def test_source_revision_requires_full_sha() -> None:
    sha = "a" * 40
    assert operator.source_revision({"observed_source_revision": sha}) == sha
    assert operator.source_revision({"build": {"git_sha": sha.upper()}}) == sha
    assert operator.source_revision({"source_revision": "abc1234"}) is None


def test_json_contracts_are_exact() -> None:
    assert operator.validate_json_contract("livez", {"status": "LIVE"})[0]
    assert not operator.validate_json_contract("livez", {"status": "starting"})[0]
    assert operator.validate_json_contract(
        "controller", {"organ": "a11oy", "locked_formula_count": 8}
    )[0]
    assert not operator.validate_json_contract(
        "controller", {"organ": "a11oy", "locked_formula_count": 7}
    )[0]


def test_vessels_card_requires_honest_markers() -> None:
    valid = b"\n".join([
        b"# Vessels \xe2\x80\x94 consolidated into Killinchu",
        b"Status: CONSOLIDATED",
        b"SZLHOLDINGS/killinchu",
        b"No live AIS feed is claimed",
    ])
    operator.validate_vessels_card(valid)
    try:
        operator.validate_vessels_card(b"Status: CONSOLIDATED")
    except operator.FrontierError:
        pass
    else:
        raise AssertionError("incomplete card must fail")


def test_private_spaces_are_never_authorized() -> None:
    rows = operator.review_private_spaces(None)
    assert [row["repo_id"].split("/", 1)[1] for row in rows] == list(
        operator.PRIVATE_SPACES
    )
    assert all(row["publication_authorized"] is False for row in rows)
    assert all(row["visibility_mutated"] is False for row in rows)


def test_metadata_boundary_is_exact() -> None:
    assert set(operator.REPOSITORY_METADATA) == {
        "szl-holdings/david-leads", "szl-holdings/szl-atelier",
    }
    assert set(operator.REPOSITORY_METADATA["szl-holdings/david-leads"]) == {
        "description"
    }
    assert set(operator.REPOSITORY_METADATA["szl-holdings/szl-atelier"]) == {
        "description", "archived",
    }
    assert operator.REPOSITORY_METADATA["szl-holdings/szl-atelier"]["archived"] is False


def test_alias_precondition_is_fail_closed() -> None:
    class FakeGitHub:
        def file_text(self, repository, path):
            assert repository == "szl-holdings/a11oy"
            assert path.endswith("a11oy-product-root-worker.mjs")
            return '{"/spectral": "/static/3d/holographic.html"}'

        def main_sha(self, repository):
            return "b" * 40

    row = operator.a11oy_alias_source_ready(FakeGitHub())
    assert row["ready"] is False
    assert '"/controller": "/api/a11oy/v1/honest"' in row["missing_markers"]


def test_dispatches_use_only_reviewed_native_workflows() -> None:
    observed = []

    class FakeGitHub:
        apply = True

        def file_text(self, repository, path):
            return "\n".join([
                '"/spectral": "/static/3d/holographic.html"',
                '"/controller": "/api/a11oy/v1/honest"',
                "READ_ONLY_METHODS",
            ])

        def main_sha(self, repository):
            return "c" * 40

        def dispatch(self, repository, workflow, inputs):
            observed.append((repository, workflow, dict(inputs)))

    rows = operator.dispatch_controls(FakeGitHub(), enabled=True)
    assert all(row["state"] == "DISPATCHED" for row in rows)
    assert observed == [
        ("szl-holdings/.github", "org-code-scanning-baseline.yml", {"apply": "true"}),
        ("szl-holdings/a11oy", "hf-sync.yml", {}),
        ("szl-holdings/a11oy", "repair-cloudflare-product-edge-production.yml", {"dry_run": "false"}),
        ("szl-holdings/szl-gpu-bridge", "nemo-v3-attempt-status.yml", {}),
    ]


def test_redaction_covers_tokens() -> None:
    value = {
        "a": "ghp_" + "a" * 30,
        "b": "hf_" + "b" * 30,
        "c": "Bearer " + "c" * 30,
    }
    redacted = json.dumps(operator.redact(value))
    assert "ghp_" not in redacted and "hf_" not in redacted
    assert "Bearer" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_terminal_status_does_not_call_dispatch_ready() -> None:
    report = {
        "repository_metadata": [{"state": "VERIFIED", "verified": True}],
        "vessels_card": {"state": "VERIFIED", "verified": True},
        "workflow_controls": [{"state": "DISPATCHED"}],
        "public_estate": {"ready": False},
    }
    assert operator.terminal_status(report) == "CONVERGENCE_DISPATCHED"
    report["public_estate"]["ready"] = True
    assert operator.terminal_status(report) == (
        "AUTOMATED_FRONTIER_COMPLETE_OWNER_SIGNATURE_REMAINS"
    )


def test_main_receipt_never_records_tokens_or_guarded_mutations() -> None:
    metadata = [
        {"repository": name, "state": "VERIFIED", "verified": True, "desired": desired}
        for name, desired in operator.REPOSITORY_METADATA.items()
    ]
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
        os.environ,
        {"SZL_ORG_TOKEN": "ghp_" + "x" * 30, "HF_TOKEN": "hf_" + "y" * 30},
        clear=True,
    ), mock.patch.object(
        operator.operator, "converge_repository_metadata", return_value=metadata
    ), mock.patch.object(
        operator.operator, "converge_vessels_card", return_value={"state": "VERIFIED", "verified": True}
    ), mock.patch.object(
        operator.operator, "review_private_spaces", return_value=[{
            "repo_id": "SZLHOLDINGS/anatomy",
            "publication_authorized": False,
            "visibility_mutated": False,
        }]
    ), mock.patch.object(
        operator.operator, "dispatch_controls", return_value=[{
            "repository": "szl-holdings/a11oy", "workflow": "hf-sync.yml", "state": "DISPATCHED"
        }]
    ), mock.patch.object(
        operator.operator, "verify_public_estate", return_value={
            "critical_verified": 8, "critical_total": 8,
            "revision_matches": True, "ready": True,
        }
    ):
        report = Path(tmp) / "report.json"
        summary = Path(tmp) / "summary.md"
        assert operator.main([
            "--report", str(report), "--summary", str(summary),
            "--apply", "--dispatch-controls", "--enforce-ready",
        ]) == 0
        text = report.read_text()
        payload = json.loads(text)
        assert ("ghp_" + "x" * 30) not in text
        assert ("hf_" + "y" * 30) not in text
        for key in (
            "token_values_recorded", "private_space_visibility_mutated",
            "branch_protection_mutated", "secrets_mutated",
            "cloudflare_mutated_by_this_controller", "nemo_signature_attempted",
            "nemo_queue_mutated",
        ):
            assert payload[key] is False
        assert payload["status"] == "AUTOMATED_FRONTIER_COMPLETE_OWNER_SIGNATURE_REMAINS"


def test_workflow_contract_is_pinned_and_visibility_safe() -> None:
    workflow = (ROOT / ".github" / "workflows" / "frontier-payload-convergence.yml").read_text()
    assert "huggingface_hub==1.19.0" in workflow
    assert "update_repo_visibility" not in workflow
    assert "private=False" not in workflow
    assert "retention-days: 90" in workflow
    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            value = stripped.split("uses:", 1)[1].split("#", 1)[0].strip()
            assert len(value.rsplit("@", 1)[-1]) == 40
            assert value.rsplit("@", 1)[-1].isalnum()


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} frontier payload convergence tests passed")
