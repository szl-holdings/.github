# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path(".github/scripts/audit_public_experience_v4.py")
WORKFLOW = Path(".github/workflows/public-experience-v4.yml")


def source() -> str:
    value = SCRIPT.read_text(encoding="utf-8")
    ast.parse(value)
    return value


def test_auditor_covers_full_public_estate_and_viewport_matrix() -> None:
    value = source()
    for target in (
        "https://a-11-oy.com/",
        "https://a11oy.net/",
        "https://szlholdings-a11oy.hf.space/",
        "https://szlholdings-killinchu.hf.space/",
        "https://szlholdings-david-leads.hf.space/",
        "https://szlholdings-terra.hf.space/",
        "https://szlholdings-sentra.hf.space/",
        "https://szlholdings-counsel.hf.space/",
        "https://szlholdings-finance.hf.space/",
        "https://szlholdings-vessels.hf.space/",
        "https://szlholdings-lyte.hf.space/",
    ):
        assert target in value
    for case in (
        'Case("phone-320", 320, 568',
        'Case("phone-375", 375, 812',
        'Case("tablet-768", 768, 1024',
        'Case("desktop-1440", 1440, 900',
        'Case("reflow-200", 640, 900, zoom=2.0)',
        'Case("reflow-400", 1280, 900, zoom=4.0)',
        'Case("reduced-motion-phone", 375, 812',
    ):
        assert case in value


def test_auditor_enforces_mobile_user_developer_and_investor_contracts() -> None:
    value = source()
    for marker in (
        "DOCUMENT_HORIZONTAL_OVERFLOW",
        "UNDERSIZED_INTERACTIVE_TARGETS",
        "KEYBOARD_PATH_MISSING",
        "FOCUS_NOT_VISIBLE",
        "LONG_MOTION_WITH_REDUCED_MOTION",
        "INTERACTIVE_VIEWPORT_OVERLAY",
        "DEVELOPER_PATH_NOT_DISCOVERABLE",
        "INVESTOR_PROOF_PATH_NOT_DISCOVERABLE",
        "MISSING_REQUIRED_MARKER",
        "UNCAUGHT_PAGE_ERROR",
        "proof_chain_sha256",
        "provider_mutations\": False",
        "service_workers=\"block\"",
    ):
        assert marker in value


def test_auditor_has_no_provider_write_or_authentication_path() -> None:
    value = source()
    for forbidden in (
        "page.fill(",
        "page.click(",
        "page.request.post(",
        "page.request.put(",
        "page.request.patch(",
        "page.request.delete(",
        "Authorization",
        "CF_API",
        "HF_TOKEN",
        "GITHUB_TOKEN",
    ):
        assert forbidden not in value


def test_workflow_is_scheduled_read_only_and_retains_evidence() -> None:
    value = WORKFLOW.read_text(encoding="utf-8")
    for marker in (
        "schedule:",
        "workflow_dispatch:",
        "permissions:",
        "contents: read",
        "issues: write",
        "playwright==1.55.0",
        "audit_public_experience_v4.py",
        "public-experience-v4-${{ github.run_id }}-${{ github.run_attempt }}",
        "retention-days: 180",
        "Update current estate issue",
    ):
        assert marker in value
    assert "contents: write" not in value
