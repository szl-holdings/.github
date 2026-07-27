#!/usr/bin/env python3
"""Materialize the protected default-branch attestor delivery repair.

This script runs only from the bounded diagnostic PR. It writes the reviewed
permanent files into the runner worktree, executes their network-free contracts,
and creates one GitHub-signed commit on a clean branch rooted at protected main.
No diagnostic controller is included in the target tree.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = os.environ["REPOSITORY"]
TARGET_BRANCH = os.environ["TARGET_BRANCH"]
EXPECTED_PARENT = os.environ["EXPECTED_PARENT"]
TOKEN = os.environ["GH_TOKEN"]

ATTESTOR_PATH = ROOT / ".github/workflows/attest-and-approve.yml"
VERIFIER_PATH = ROOT / ".github/scripts/verify_forge9_governance.py"
TESTS_WORKFLOW_PATH = ROOT / ".github/workflows/tests.yml"
CONTRACT_PATH = ROOT / ".github/scripts/test_attestor_delivery.py"

ATTESTOR = r'''name: FORGE-9 attest and approve

on:
  workflow_run:
    workflows:
      - FORGE-9 gates
    types:
      - completed
  workflow_dispatch:
    inputs:
      pull_request:
        description: "Exact open pull request number"
        required: true
        type: string
      head_sha:
        description: "Exact 40-character pull request head SHA"
        required: true
        type: string
      gate_run_id:
        description: "Successful FORGE-9 gates workflow run ID for the exact head"
        required: true
        type: string
  schedule:
    - cron: "*/5 * * * *"

permissions:
  actions: write
  contents: write
  id-token: write
  pull-requests: write

concurrency:
  group: forge9-attest-${{ github.event.workflow_run.head_sha || inputs.head_sha || github.run_id }}
  cancel-in-progress: false

jobs:
  attest:
    if: >-
      (github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success') ||
      github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      SUBJECT_HEAD_SHA: ${{ github.event.workflow_run.head_sha || inputs.head_sha }}
      SUBJECT_HEAD_BRANCH: ${{ github.event.workflow_run.head_branch || '' }}
      SUBJECT_SOURCE_EVENT: ${{ github.event.workflow_run.event || 'pull_request' }}
      SUBJECT_SOURCE_RUN_ID: ${{ github.event.workflow_run.id || inputs.gate_run_id }}
    steps:
      - name: Mint the independent App token
        id: app-token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          client-id: ${{ vars.QILLQAQ_CLIENT_ID }}
          private-key: ${{ secrets.QILLQAQ_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: ${{ github.event.repository.name }}

      - name: Resolve the attestation subject
        id: subject
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
          HEAD_BRANCH: ${{ env.SUBJECT_HEAD_BRANCH }}
          SOURCE_EVENT: ${{ env.SUBJECT_SOURCE_EVENT }}
          SOURCE_RUN_ID: ${{ env.SUBJECT_SOURCE_RUN_ID }}
          DISPATCH_PR: ${{ inputs.pull_request || '' }}
          REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          if [ -n "$DISPATCH_PR" ]; then
            [[ "$DISPATCH_PR" =~ ^[0-9]+$ ]] \
              || { echo "::error::dispatch pull_request is not numeric"; exit 1; }
            [[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]] \
              || { echo "::error::dispatch head_sha is not canonical"; exit 1; }
            [[ "$SOURCE_RUN_ID" =~ ^[0-9]+$ ]] \
              || { echo "::error::dispatch gate_run_id is not numeric"; exit 1; }

            gh api "repos/$REPOSITORY/actions/runs/$SOURCE_RUN_ID" \
              > "$RUNNER_TEMP/source-run.json"
            [ "$(jq -r .name "$RUNNER_TEMP/source-run.json")" = "FORGE-9 gates" ] \
              || { echo "::error::dispatch source is not FORGE-9 gates"; exit 1; }
            [ "$(jq -r .event "$RUNNER_TEMP/source-run.json")" = "pull_request" ] \
              || { echo "::error::dispatch source event is not pull_request"; exit 1; }
            [ "$(jq -r .conclusion "$RUNNER_TEMP/source-run.json")" = "success" ] \
              || { echo "::error::dispatch source run is not successful"; exit 1; }
            [ "$(jq -r .head_sha "$RUNNER_TEMP/source-run.json")" = "$HEAD_SHA" ] \
              || { echo "::error::dispatch source head mismatch"; exit 1; }
            [ "$(jq -r .head_repository.full_name "$RUNNER_TEMP/source-run.json")" = "$REPOSITORY" ] \
              || { echo "::error::dispatch source repository mismatch"; exit 1; }

            gh api "repos/$REPOSITORY/pulls/$DISPATCH_PR" > "$RUNNER_TEMP/pr.json"
            [ "$(jq -r .state "$RUNNER_TEMP/pr.json")" = "open" ] \
              || { echo "::error::dispatch PR is not open"; exit 1; }
            [ "$(jq -r .draft "$RUNNER_TEMP/pr.json")" = "false" ] \
              || { echo "::error::dispatch PR is draft"; exit 1; }
            [ "$(jq -r .head.sha "$RUNNER_TEMP/pr.json")" = "$HEAD_SHA" ] \
              || { echo "::error::dispatch PR head mismatch"; exit 1; }
            [ "$(jq -r .head.repo.full_name "$RUNNER_TEMP/pr.json")" = "$REPOSITORY" ] \
              || { echo "::error::dispatch PR is cross-repository"; exit 1; }
            BASE_REF="$(jq -r .base.ref "$RUNNER_TEMP/pr.json")"
            { [ "$BASE_REF" = "main" ] || [[ "$BASE_REF" == release/* ]]; } \
              || { echo "::error::dispatch PR base is not governed"; exit 1; }
            echo "kind=pull_request" >> "$GITHUB_OUTPUT"
            echo "number=$DISPATCH_PR" >> "$GITHUB_OUTPUT"
            echo "node_id=$(jq -r .node_id "$RUNNER_TEMP/pr.json")" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          if [ "$SOURCE_EVENT" = "merge_group" ]; then
            [[ "$HEAD_BRANCH" == gh-readonly-queue/main/* ]] \
              || { echo "::error::unexpected merge-group branch: $HEAD_BRANCH"; exit 1; }
            echo "kind=merge_group" >> "$GITHUB_OUTPUT"
            echo "number=" >> "$GITHUB_OUTPUT"
            echo "node_id=" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          [ "$SOURCE_EVENT" = "pull_request" ] \
            || { echo "::error::unsupported source event: $SOURCE_EVENT"; exit 1; }

          gh api \
            -H "Accept: application/vnd.github+json" \
            "repos/$REPOSITORY/commits/$HEAD_SHA/pulls?per_page=100" \
            > "$RUNNER_TEMP/pulls.json"
          mapfile -t PRS < <(
            jq -r --arg sha "$HEAD_SHA" \
              '.[] | select(
                .state == "open"
                and .head.sha == $sha
                and (
                  .base.ref == "main"
                  or (.base.ref | startswith("release/"))
                )
              ) | .number' \
              "$RUNNER_TEMP/pulls.json"
          )
          if [ "${#PRS[@]}" -ne 1 ]; then
            echo "::error::expected exactly one open main or release/* PR for $HEAD_SHA; found ${#PRS[@]}"
            exit 1
          fi
          PR="${PRS[0]}"
          gh api "repos/$REPOSITORY/pulls/$PR" > "$RUNNER_TEMP/pr.json"
          echo "kind=pull_request" >> "$GITHUB_OUTPUT"
          echo "number=$PR" >> "$GITHUB_OUTPUT"
          echo "node_id=$(jq -r .node_id "$RUNNER_TEMP/pr.json")" >> "$GITHUB_OUTPUT"

      - name: Verify gates and preconditions P1-P7
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
          SUBJECT_KIND: ${{ steps.subject.outputs.kind }}
          PR: ${{ steps.subject.outputs.number }}
          REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          if [ "$SUBJECT_KIND" = "pull_request" ]; then
            BODY=$(jq -r '.body // ""' "$RUNNER_TEMP/pr.json")

            grep -Eq 'Satisfies:[[:space:]]*(AT-[0-9]+|C-[0-9]+)' <<<"$BODY" \
              || { echo "::error::P1 missing Satisfies: AT-n or C-n"; exit 1; }
            grep -Eq 'Rollback:[[:space:]]*\S' <<<"$BODY" \
              || { echo "::error::P2 missing Rollback"; exit 1; }
            grep -Eq 'Labels:[[:space:]]*\S' <<<"$BODY" \
              || { echo "::error::P3 missing Labels"; exit 1; }
            grep -Eq 'Risk:[[:space:]]*[ABCD][[:space:]]*[-—]' <<<"$BODY" \
              || { echo "::error::missing Risk: A-D classification"; exit 1; }

            gh api "repos/$REPOSITORY/pulls/$PR/files?per_page=100" --paginate \
              --jq '.[].filename' > "$RUNNER_TEMP/files.txt"
            if grep -Eq '^(\.github/workflows/(attest-and-approve|gates|forge9-staging|merge-queue-enqueue)\.ya?ml|\.governance/)' \
                "$RUNNER_TEMP/files.txt"; then
              grep -Eq 'Solo-Operator-Authorization:[[:space:]]*confirmed' <<<"$BODY" \
                || { echo "::error::P5 governance change lacks solo-operator authorization"; exit 1; }
              grep -Eq 'Risk:[[:space:]]*D[[:space:]]*[-â€”]' <<<"$BODY" \
                || { echo "::error::P5 governance change must be classified Risk D"; exit 1; }
            fi
          fi

          gh api \
            -H "Accept: application/vnd.github+json" \
            "repos/$REPOSITORY/commits/$HEAD_SHA/check-runs?filter=latest&per_page=100" \
            > "$RUNNER_TEMP/check-runs.json"
          REQUIRED=(
            gate/ground-truth
            gate/labels
            gate/schema
            gate/adversarial
            gate/verify-all
            gate/provenance
            gate/a11y-perf
            gate/lean
          )
          for CHECK in "${REQUIRED[@]}"; do
            COUNT=$(jq --arg check "$CHECK" \
              '[.check_runs[] | select(.name == $check and .conclusion == "success")] | length' \
              "$RUNNER_TEMP/check-runs.json")
            [ "$COUNT" -ge 1 ] \
              || { echo "::error::required check is not green: $CHECK"; exit 1; }
          done

          HAS_QUEUE=0
          gh api "repos/$REPOSITORY/rulesets?per_page=100" --paginate \
            --jq '.[].id' > "$RUNNER_TEMP/ruleset-ids.txt"
          [ -s "$RUNNER_TEMP/ruleset-ids.txt" ] \
            || { echo "::error::P6 found no rulesets"; exit 1; }
          while read -r ID; do
            gh api "repos/$REPOSITORY/rulesets/$ID" > "$RUNNER_TEMP/ruleset-$ID.json"
            BYPASS=$(jq '.bypass_actors | length' "$RUNNER_TEMP/ruleset-$ID.json")
            [ "$BYPASS" -eq 0 ] \
              || { echo "::error::P6 ruleset $ID has $BYPASS bypass actors"; exit 1; }
            if jq -e '.rules[] | select(.type == "merge_queue")' \
                "$RUNNER_TEMP/ruleset-$ID.json" >/dev/null; then
              HAS_QUEUE=1
            fi
          done < "$RUNNER_TEMP/ruleset-ids.txt"
          [ "$HAS_QUEUE" -eq 1 ] \
            || { echo "::error::merge queue rule is not active"; exit 1; }

          CAN_APPROVE=$(gh api "repos/$REPOSITORY/actions/permissions/workflow" \
            --jq '.can_approve_pull_request_reviews')
          [ "$CAN_APPROVE" = "false" ] \
            || { echo "::error::P7 default GITHUB_TOKEN can approve reviews"; exit 1; }

      - name: Build and sign the merge BAP
        env:
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
          SUBJECT_KIND: ${{ steps.subject.outputs.kind }}
          PR: ${{ steps.subject.outputs.number }}
          REPOSITORY: ${{ github.repository }}
          SOURCE_RUN_ID: ${{ env.SUBJECT_SOURCE_RUN_ID }}
          DELIVERY_MODE: ${{ github.event_name }}
          ATTESTOR_RUN_ID: ${{ github.run_id }}
        run: |
          set -euo pipefail
          jq -n \
            --arg schema "https://a11oy.net/schemas/forge9/merge-bap/v1" \
            --arg repository "$REPOSITORY" \
            --arg subject_kind "$SUBJECT_KIND" \
            --arg pull_request "$PR" \
            --arg head_sha "$HEAD_SHA" \
            --arg principal "spiffe://a11oy.net/ns/ci/sa/qillqaq-attestor" \
            --arg policy_id "merge-gate-v1" \
            --arg source_run_id "$SOURCE_RUN_ID" \
            --arg delivery_mode "$DELIVERY_MODE" \
            --arg attestor_run_id "$ATTESTOR_RUN_ID" \
            --arg issued_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            --slurpfile checks "$RUNNER_TEMP/check-runs.json" \
            '{
              schema: $schema,
              repository: $repository,
              subject_kind: $subject_kind,
              pull_request: (
                if $pull_request == ""
                then null
                else ($pull_request | tonumber)
                end
              ),
              head_sha: $head_sha,
              principal: $principal,
              policy_id: $policy_id,
              source_workflow_run_id: $source_run_id,
              attestor_run_id: $attestor_run_id,
              delivery_mode: $delivery_mode,
              issued_at: $issued_at,
              checks: [
                $checks[0].check_runs[]
                | select(.name | startswith("gate/"))
                | {name, conclusion, details_url}
              ],
              breakglass: null
            }' > merge-receipt.json

      - name: Install Cosign
        uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2

      - name: Sign the merge BAP with Actions OIDC
        run: cosign sign-blob --yes --bundle merge-receipt.bundle merge-receipt.json

      - name: Upload the signed merge BAP
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: merge-receipt-${{ env.SUBJECT_HEAD_SHA }}
          path: |
            merge-receipt.json
            merge-receipt.bundle
          if-no-files-found: error
          retention-days: 90

      - name: Approve as the App and verify the review identity
        if: steps.subject.outputs.kind == 'pull_request'
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
          PR: ${{ steps.subject.outputs.number }}
          REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          DIGEST=$(sha256sum merge-receipt.json | cut -d' ' -f1)
          gh api -X POST "repos/$REPOSITORY/pulls/$PR/reviews" \
            -f event=APPROVE \
            -f body="ATTESTED. All Section 18 gates green. Merge BAP sha256: $DIGEST"
          COUNT=$(gh api "repos/$REPOSITORY/pulls/$PR/reviews?per_page=100" --paginate \
            --jq "[.[] | select(.user.login == \"qillqaq-attestor[bot]\" and .state == \"APPROVED\" and .commit_id == \"$HEAD_SHA\")] | length")
          [ "$COUNT" -ge 1 ] \
            || { echo "::error::App approval was not recorded for the exact head SHA"; exit 1; }

      - name: Publish required App attestation status
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
          SUBJECT_KIND: ${{ steps.subject.outputs.kind }}
          REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          if [ "$SUBJECT_KIND" = "pull_request" ]; then
            DESCRIPTION="Signed BAP and exact-head App review verified"
          else
            DESCRIPTION="Signed BAP verified for merge-group gates"
          fi
          gh api \
            --method POST \
            "repos/$REPOSITORY/statuses/$HEAD_SHA" \
            -f state=success \
            -f context=attestation/qillqaq \
            -f description="$DESCRIPTION" \
            -f target_url="https://github.com/$REPOSITORY/actions/runs/$GITHUB_RUN_ID"
          echo "Published attestation/qillqaq for $HEAD_SHA"

      - name: Hand off to protected native enqueue controller
        if: steps.subject.outputs.kind == 'pull_request'
        env:
          PR: ${{ steps.subject.outputs.number }}
          HEAD_SHA: ${{ env.SUBJECT_HEAD_SHA }}
        run: |
          set -euo pipefail
          echo "Exact-head qillqaq evidence is published for PR $PR at $HEAD_SHA."
          echo "Protected Merge Queue Enqueue owns native enqueuePullRequest delivery."

  recover-missed-delivery:
    name: Recover missed workflow-run delivery from protected main
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Mint qillqaq read identity
        id: recovery-app-token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          client-id: ${{ vars.QILLQAQ_CLIENT_ID }}
          private-key: ${{ secrets.QILLQAQ_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: ${{ github.event.repository.name }}

      - name: Dispatch exact heads whose workflow-run delivery was missed
        env:
          READ_TOKEN: ${{ steps.recovery-app-token.outputs.token }}
          DISPATCH_TOKEN: ${{ github.token }}
          REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          mkdir -p "$RUNNER_TEMP/attestor-recovery"
          GH_TOKEN="$READ_TOKEN" gh api \
            "repos/$REPOSITORY/pulls?state=open&per_page=100" \
            --paginate --slurp > "$RUNNER_TEMP/attestor-recovery/pull-pages.json"
          jq -c --arg repo "$REPOSITORY" '[.[][] | select(
            .draft == false
            and .head.repo.full_name == $repo
            and (.base.ref == "main" or (.base.ref | startswith("release/")))
          )] | .[]' "$RUNNER_TEMP/attestor-recovery/pull-pages.json" \
            > "$RUNNER_TEMP/attestor-recovery/targets.jsonl"

          dispatched=0
          skipped=0
          while IFS= read -r target; do
            PR="$(jq -r .number <<<"$target")"
            HEAD_SHA="$(jq -r .head.sha <<<"$target")"
            GH_TOKEN="$READ_TOKEN" gh api \
              "repos/$REPOSITORY/pulls/$PR/reviews?per_page=100" \
              > "$RUNNER_TEMP/attestor-recovery/reviews-$PR.json"
            APPROVALS="$(jq --arg head "$HEAD_SHA" '[.[] | select(
              (.user.login == "qillqaq-attestor[bot]" or .user.login == "qillqaq-attestor")
              and .state == "APPROVED"
              and .commit_id == $head
            )] | length' "$RUNNER_TEMP/attestor-recovery/reviews-$PR.json")"
            GH_TOKEN="$READ_TOKEN" gh api \
              "repos/$REPOSITORY/commits/$HEAD_SHA/status" \
              > "$RUNNER_TEMP/attestor-recovery/status-$PR.json"
            STATUSES="$(jq '[.statuses[] | select(
              .context == "attestation/qillqaq" and .state == "success"
            )] | length' "$RUNNER_TEMP/attestor-recovery/status-$PR.json")"
            if [ "$APPROVALS" -ge 1 ] && [ "$STATUSES" -ge 1 ]; then
              skipped=$((skipped + 1))
              continue
            fi

            GH_TOKEN="$READ_TOKEN" gh api \
              "repos/$REPOSITORY/actions/workflows/gates.yml/runs?event=pull_request&head_sha=$HEAD_SHA&per_page=100" \
              > "$RUNNER_TEMP/attestor-recovery/gates-$PR.json"
            GATE_RUN_ID="$(jq -r --arg head "$HEAD_SHA" --arg repo "$REPOSITORY" '[
              .workflow_runs[] | select(
                .head_sha == $head
                and .event == "pull_request"
                and .conclusion == "success"
                and .head_repository.full_name == $repo
              )
            ] | sort_by(.created_at) | last | .id // empty' \
              "$RUNNER_TEMP/attestor-recovery/gates-$PR.json")"
            if [ -z "$GATE_RUN_ID" ]; then
              skipped=$((skipped + 1))
              continue
            fi
            GH_TOKEN="$DISPATCH_TOKEN" gh workflow run attest-and-approve.yml \
              --repo "$REPOSITORY" \
              --ref main \
              -f pull_request="$PR" \
              -f head_sha="$HEAD_SHA" \
              -f gate_run_id="$GATE_RUN_ID"
            dispatched=$((dispatched + 1))
          done < "$RUNNER_TEMP/attestor-recovery/targets.jsonl"

          jq -n \
            --arg schema 'szl.attestor-delivery-recovery/v1' \
            --argjson dispatched "$dispatched" \
            --argjson skipped "$skipped" \
            '{
              schema: $schema,
              dispatched: $dispatched,
              skipped: $skipped,
              default_branch_code: true,
              pull_request_target_used: false,
              custom_secret_value_recorded: false
            }' > attestor-delivery-recovery.json
          cat attestor-delivery-recovery.json

      - name: Upload immutable recovery receipt
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: attestor-delivery-recovery-${{ github.run_id }}
          path: attestor-delivery-recovery.json
          if-no-files-found: error
          retention-days: 90
'''

CONTRACT = r'''#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ATTESTOR = ROOT / ".github/workflows/attest-and-approve.yml"
ENQUEUE = ROOT / ".github/workflows/merge-queue-enqueue.yml"


class AttestorDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.attestor = ATTESTOR.read_text(encoding="utf-8")
        cls.enqueue = ENQUEUE.read_text(encoding="utf-8")

    def test_default_branch_has_immediate_and_recovery_delivery(self) -> None:
        for marker in (
            "workflow_run:",
            "workflow_dispatch:",
            "schedule:",
            "Recover missed workflow-run delivery from protected main",
            "gh workflow run attest-and-approve.yml",
        ):
            self.assertIn(marker, self.attestor)

    def test_dispatch_tuple_is_revalidated(self) -> None:
        for marker in (
            "dispatch pull_request is not numeric",
            "dispatch head_sha is not canonical",
            "dispatch gate_run_id is not numeric",
            "dispatch source is not FORGE-9 gates",
            "dispatch source head mismatch",
            "dispatch PR head mismatch",
            "dispatch PR is cross-repository",
        ):
            self.assertIn(marker, self.attestor)

    def test_qillqaq_remains_default_branch_only(self) -> None:
        self.assertIn("secrets.QILLQAQ_PRIVATE_KEY", self.attestor)
        self.assertNotIn("pull_request_target", self.attestor)
        self.assertNotIn("QILLQAQ_PRIVATE_KEY", self.enqueue)

    def test_attestor_never_merges_or_enqueues(self) -> None:
        self.assertNotIn("gh pr merge", self.attestor)
        self.assertNotIn("enqueuePullRequest", self.attestor)
        self.assertIn("enqueuePullRequest", self.enqueue)
        self.assertIn("Hand off to protected native enqueue controller", self.attestor)

    def test_recovery_receipt_contains_no_secret_material(self) -> None:
        for marker in (
            "default_branch_code: true",
            "pull_request_target_used: false",
            "custom_secret_value_recorded: false",
            "retention-days: 90",
        ):
            self.assertIn(marker, self.attestor)
        self.assertNotIn("set -x", self.attestor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
'''


def patch_verifier(source: str) -> str:
    source = source.replace(
        r'^(\.github/workflows/(attest-and-approve|gates|forge9-staging)'
        r'\.ya?ml|\.governance/)',
        r'^(\.github/workflows/(attest-and-approve|gates|forge9-staging|merge-queue-enqueue)'
        r'\.ya?ml|\.governance/)',
        1,
    )
    source = source.replace(
        '        ".github/workflows/forge9-staging.yaml",\n'
        '        ".governance/gates.json",\n',
        '        ".github/workflows/forge9-staging.yaml",\n'
        '        ".github/workflows/merge-queue-enqueue.yml",\n'
        '        ".github/workflows/merge-queue-enqueue.yaml",\n'
        '        ".governance/gates.json",\n',
        1,
    )
    old = '''    if GOVERNED_BASE_FILTER not in attestor_template:
        fail("attestor must resolve PRs targeting main and release/*")
    if "environment: production" in attestor_template:
        fail("the merge attestor must not consume the production deployment gate")
    if "GH_TOKEN: ${{ github.token }}" not in attestor_template:
        fail("the protected queue request must use the ephemeral workflow token")
    for marker in (
        "Publish required App attestation status",
        "context=attestation/qillqaq",
        "GH_TOKEN: ${{ steps.app-token.outputs.token }}",
        "client-id: ${{ vars.QILLQAQ_CLIENT_ID }}",
        'SOURCE_EVENT: ${{ github.event.workflow_run.event }}',
        'if [ "$SOURCE_EVENT" = "merge_group" ]; then',
        '[[ "$HEAD_BRANCH" == gh-readonly-queue/main/* ]]',
        "subject_kind: $subject_kind",
    ):
        if marker not in attestor_template:
            fail(f"attestor status publication is missing {marker!r}")
    if "app-id:" in attestor_template:
        fail("the attestor must use the supported GitHub App client-id input")
    if attestor_template.count(
        "if: steps.subject.outputs.kind == 'pull_request'"
    ) != 2:
        fail("only PR-head attestations may approve or request a queue entry")
    if 'gh pr merge "$PR" --repo "$REPOSITORY" --auto --squash' not in (
        attestor_template
    ):
        fail("the attestor must use GitHub's supported merge-queue CLI path")
'''
    new = '''    if GOVERNED_BASE_FILTER not in attestor_template:
        fail("attestor must resolve PRs targeting main and release/*")
    if "environment: production" in attestor_template:
        fail("the merge attestor must not consume the production deployment gate")
    enqueue_template = (
        ROOT / ".github/workflows/merge-queue-enqueue.yml"
    ).read_text(encoding="utf-8")
    for marker in (
        "Publish required App attestation status",
        "context=attestation/qillqaq",
        "GH_TOKEN: ${{ steps.app-token.outputs.token }}",
        "client-id: ${{ vars.QILLQAQ_CLIENT_ID }}",
        "workflow_dispatch:",
        "schedule:",
        "Recover missed workflow-run delivery from protected main",
        "gh workflow run attest-and-approve.yml",
        "SUBJECT_HEAD_SHA: ${{ github.event.workflow_run.head_sha || inputs.head_sha }}",
        "DISPATCH_PR: ${{ inputs.pull_request || '' }}",
        "source_workflow_run_id",
        'if [ "$SOURCE_EVENT" = "merge_group" ]; then',
        '[[ "$HEAD_BRANCH" == gh-readonly-queue/main/* ]]',
        "subject_kind: $subject_kind",
        "Hand off to protected native enqueue controller",
    ):
        if marker not in attestor_template:
            fail(f"attestor delivery contract is missing {marker!r}")
    if "app-id:" in attestor_template:
        fail("the attestor must use the supported GitHub App client-id input")
    if attestor_template.count(
        "if: steps.subject.outputs.kind == 'pull_request'"
    ) != 2:
        fail("only PR-head attestations may approve or hand off to native enqueue")
    if "gh pr merge" in attestor_template or "enqueuePullRequest" in attestor_template:
        fail("the attestor must not merge or enqueue; native enqueue owns that mutation")
    if "enqueuePullRequest" not in enqueue_template:
        fail("the protected native enqueue controller is missing")
    if "pull_request_target" in attestor_template:
        fail("attestor recovery must never use pull_request_target")
'''
    if old not in source:
        raise SystemExit("governance verifier contract changed unexpectedly")
    return source.replace(old, new, 1)


def patch_tests_workflow(source: str) -> str:
    marker = (
        "      - name: HF deploy-from-Dockerfile derivation self-test\n"
        "        run: python3 .github/scripts/test_hf_deploy_from_dockerfile.py\n"
    )
    if marker not in source:
        raise SystemExit("tests workflow tail changed unexpectedly")
    return source.replace(
        marker,
        marker
        + "\n      # Pins protected-main recovery when workflow_run delivery is omitted.\n"
        + "      - name: Attestor delivery recovery contract self-test\n"
        + "        run: python3 .github/scripts/test_attestor_delivery.py\n",
        1,
    )


def request(url: str, *, data: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        data=(json.dumps(data).encode("utf-8") if data is not None else None),
        method=("POST" if data is not None else "GET"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-attestor-delivery-materializer/2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc


def main() -> int:
    ATTESTOR_PATH.write_text(ATTESTOR, encoding="utf-8")
    CONTRACT_PATH.write_text(CONTRACT, encoding="utf-8")
    VERIFIER_PATH.write_text(
        patch_verifier(VERIFIER_PATH.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    TESTS_WORKFLOW_PATH.write_text(
        patch_tests_workflow(TESTS_WORKFLOW_PATH.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    subprocess.run(
        [
            "python",
            "-m",
            "py_compile",
            str(VERIFIER_PATH),
            str(CONTRACT_PATH),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["python", str(CONTRACT_PATH)], cwd=ROOT, check=True)
    subprocess.run(["python", str(VERIFIER_PATH)], cwd=ROOT, check=True)
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)

    additions = [
        ".github/workflows/attest-and-approve.yml",
        ".github/scripts/verify_forge9_governance.py",
        ".github/scripts/test_attestor_delivery.py",
        ".github/workflows/tests.yml",
    ]
    mutation = '''
    mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid url }
      }
    }
    '''
    variables = {
        "input": {
            "branch": {
                "repositoryNameWithOwner": REPOSITORY,
                "branchName": TARGET_BRANCH,
            },
            "message": {
                "headline": "fix(attestor): recover missed gate delivery",
                "body": "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
            },
            "expectedHeadOid": EXPECTED_PARENT,
            "fileChanges": {
                "additions": [
                    {
                        "path": path,
                        "contents": base64.b64encode((ROOT / path).read_bytes()).decode(
                            "ascii"
                        ),
                    }
                    for path in additions
                ]
            },
        }
    }
    payload = request(
        "https://api.github.com/graphql",
        data={"query": mutation, "variables": variables},
    )
    if payload.get("errors"):
        raise SystemExit(json.dumps(payload["errors"], indent=2))
    commit = payload["data"]["createCommitOnBranch"]["commit"]
    sha = commit["oid"]

    verification = request(f"https://api.github.com/repos/{REPOSITORY}/commits/{sha}")[
        "commit"
    ]["verification"]
    if verification.get("verified") is not True or verification.get("reason") != "valid":
        raise SystemExit(f"target commit is not GitHub-verified: {verification}")

    receipt = {
        "schema": "szl.attestor-delivery-materialization/v1",
        "parent": EXPECTED_PARENT,
        "target_branch": TARGET_BRANCH,
        "commit": commit,
        "verification": {
            "verified": verification.get("verified"),
            "reason": verification.get("reason"),
        },
        "files": additions,
        "diagnostic_controller_included": False,
    }
    (ROOT / "signed-attestor-delivery.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
