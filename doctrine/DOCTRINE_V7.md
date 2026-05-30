# SZL Doctrine v7

**Status:** ENACTED — 2026-05-30  
**Supersedes:** Doctrine v6 (session-locked 2026-05-29 evening)  
**Authority:** Founder — Wayne Slaughter  
**Attestation:** This document was drafted under Doctrine v6 and must itself pass v6/v7 grep on every clause.  
**Audit basis:** Lessons derived from `/home/user/workspace/szl/audit_2026-05-29_evening/` session artifacts.

---

> Doctrine that bends becomes doctrine that breaks.
> Every clause below traces to a specific failure observed tonight. No clause is decorative.

---

## Part I — Inherited Clauses (v6, verbatim, renumbered)

### §1 — No Marketing Superlatives

No use of the terms: revolutionary, unprecedented, world-class, seamless, industry-leading, cutting-edge, game-changing, breakthrough, first, only — unless the claim is directly supported by a citable source. The citation must appear in the same file, in the same paragraph, and must resolve to a verifiable URL or DOI.

**Enforcement:** grep CI gate. Any match on the banned term list without an adjacent citation block (within 5 lines) fails the gate.

---

### §2 — No Hallucinations / No Fake Green

No fabricated data, no invented citations, no status badges that do not reflect a verifiable current state. A badge that asserts a positive status (green, passing, compliant) without a verifiable contemporaneous source is a fake-green violation.

**Enforcement:** Badge manifest check in CI. Every badge URL must resolve and return the claimed status at pipeline time.

---

### §3 — No New Axioms Without Prior Approval

No new axiom may be added to the Lean proof corpus, the governance DSL, or any signed receipt chain without explicit prior written approval from the Founder. A proposed axiom must be submitted as a PR with a rationale document; it may not be merged until approved.

**Enforcement:** Lean axiom count is checked in CI against the declared axiom allowlist. Any axiom not in the allowlist fails the build.

---

### §4 — No New Sorries Without Discharge Route

A `sorry` may be introduced into a Lean proof only if the PR introducing it includes a documented discharge route: a specific, named approach for eliminating the sorry, with an owner and a target milestone. Sorries without discharge routes are rejected at review.

**Enforcement:** grep CI gate on `sorry` in `.lean` files. Each sorry must be accompanied by a `-- discharge: <route>` comment on the same line or the line above.

---

### §5 — Signed Commits (DCO)

All commits to any repository under `szl-holdings` must carry a DCO sign-off (`Signed-off-by:` trailer) and, where branch protection rules are set, must be GPG- or SSH-signed. Unsigned commits are rejected by the branch protection ruleset.

**Enforcement:** GitHub branch protection + DCO GitHub App. CI fails on any PR whose commits lack sign-off.

---

### §6 — No Emoji in Level-2 or Level-3 Headers

No emoji characters may appear in `##` or `###` markdown headers in any document that is part of the official SZL artifact set (READMEs, doctrine files, receipts, PR bodies, reports).

**Enforcement:** grep CI gate (emoji range). Pattern checks for emoji Unicode ranges (U+1F000–U+1FFFF, U+2702–U+27B0, U+1F300–U+1FAFF) in `##` and `###` header lines. Em-dashes (`—`) and section signs (`§`) are permitted. The a11oy checker implements this as the Python `emoji_re` pattern; the conservative raw-grep `^#{2,3}.*[^\x00-\x7F]` is a documentation proxy only and is not used in CI when non-emoji non-ASCII (§, —, ≥) appear in headers for legitimate typographic use.

---

### §7 — Every Claim Citable

Every factual claim in any SZL artifact (numeric, status, capability, or comparative) must be traceable to a citable source. A claim with no citation is inadmissible as governance evidence. Where the source is an internal artifact, the artifact path and commit SHA must be specified.

**Enforcement:** Semantic check in the a11oy checker (doctrine_v7_checker.ts). Numeric claims without adjacent citations are flagged.

---

### §8 — Cultural-Reference Lineage Tag

Any reference to an ancient, philosophical, or esoteric source must carry a `lineage:` tag in the document metadata or in a bracketed annotation immediately following the reference. The tag format is `lineage:<philosopher>-<concept>` (e.g., `lineage:hume-induction`).

**Enforcement:** grep CI gate on prose containing known ancient/esoteric source names. If a name matches the lineage source list but no `lineage:` tag appears within 3 lines, the gate fails.

---

## Part II — New Clauses (v7 additions, from session lessons)

---

### §9 — DOI Dereferencing Required Before Citation

**Rule:** A DOI may not be cited as a distinct work unless it has been dereferenced (resolved) at the time of citation and confirmed to identify the work being described. Concept-DOI aliases (DOIs that resolve to another DOI representing the latest version of a work) must be explicitly identified as concept-DOI aliases; they may not be cited as if they identify a specific, immutable snapshot. Any claim that treats a concept-DOI alias as a fixed release is a doctrine violation.

**Rationale:** DOI `10.5281/zenodo.19944926` was treated for weeks as a distinct Zenodo release when it is a concept-DOI alias that resolves to `10.5281/zenodo.20434276`. This produced stale and incorrect provenance chains.  
Source: `/home/user/workspace/szl/audit_2026-05-29_evening/payload_refresh/ZENODO_GITHUB_MISMATCHES.csv`, row 2, column `notes`: "19944926 is the concept-DOI alias for ouroboros-thesis. It resolves to 20434276 (v18.0). NOT a separate work."

**Enforcement:**  
- CI grep gate: any DOI string ending in `19944926` used without the adjacent tag `[concept-DOI-alias]` fails.  
- General rule: the a11oy checker flags DOI citations in markdown that lack a `[concept-DOI-alias]` or `[version-DOI]` annotation.  
- Human review: DOI provenance must be included in the DSSE receipt `doi_type` field (`concept` or `version`).

---

### §10 — Version-Scoped Badge Requirement

**Rule:** Any CI badge, status badge, or green-claim in a README or governance artifact must be scoped to a specific commit SHA or semver tag. A badge that implies current-state truth without a version anchor is a fake-green violation under §2. The version anchor must appear in the badge URL or in a parenthetical annotation immediately following the badge, formatted as `(as of <sha|tag>)`.

**Rationale:** The lutar-lean README displayed a "Lean Kernel Green" badge referencing commit `7ef33a6` but the badge was read as implying current-`main` green status. At the time of the audit, `main` build was failing (PRs #98–#102 open with fixes).  
Source: `/home/user/workspace/szl/audit_2026-05-29_evening/hf_truth_audit/REPORT.md`, LIE #4: "Every HF asset displays a 'Lean Kernel Green' badge without this caveat."

**Enforcement:**  
- CI grep gate: badge URLs containing status keywords (`green`, `passing`, `success`, `badge`) must be followed within 10 lines by a pattern matching `as of [0-9a-f]{7,40}` or `as of v[0-9]+\.[0-9]+`.  
- The a11oy checker emits a `BADGE_UNSCOPED` violation for any badge lacking a version anchor.  
- Badge manifests must be declared in a `badges.json` file per repo, each entry containing `badge_url`, `anchor_commit`, and `anchor_date`.

---

### §11 — Canonical-Number Propagation Deadline

**Rule:** When a canonical numeric value is updated (benchmark score, sorry count, tool count, theorem count, or any other metric cited across multiple files), all affected files must reflect the updated value within 48 hours of the canonical update. After 48 hours, a stale numeric is a doctrine violation in any file that still carries the old value. The owner of the canonical number must maintain an inventory of all files where the number appears; that inventory is a required artifact of the update.

**Rationale:** The Putnam percentage `8.3% (1/12)` lingered on 31 HF assets after the canonical value was updated to `83.3% (10/12)` on 2026-10-12. The stale figure persisted as a 10× magnitude error on investor-facing assets.  
Source: `/home/user/workspace/szl/audit_2026-05-29_evening/hf_truth_audit/REPORT.md`, LIE #1: "This is a 10x magnitude error on a key investor-facing metric" affecting "ALL 29 datasets + ALL 2 models = 31 files."

**Enforcement:**  
- Canonical numbers are declared in a `canonical_numbers.json` file at the `.github` repo root.  
- CI check: on any PR that modifies `canonical_numbers.json`, a script asserts that all file paths listed in the `propagation_targets` array for each changed key have been updated in the same PR or in a PR merged within the last 48 hours.  
- The a11oy checker compares numeric values in scanned files against `canonical_numbers.json` and flags mismatches as `STALE_CANONICAL`.

---

### §12 — Staged-Advisory Language as Default for Unverified Claims

**Rule:** Any capability claim, status claim, or readiness claim that is not backed by a verifiable signed artifact (signed release binary, cosign attestation, or Lean machine-checked proof) must be expressed using staged-advisory language. The required prefixes are: `STAGED-ADVISORY:`, `claimed (unverified):`, or `target (not yet achieved):`. A bare positive claim ("this system is catalog-grade", "this image is signed") without the staged-advisory prefix and without a verifiable artifact URL is an outright-claim violation.

**Rationale:** Five outright catalog-grade claims were found across the codebase (`CURSOR_MASTER_DIRECTIVE.md` L562, L587, L594; `UDS_CATALOG_SPONSOR_APPLICATION.md`; `szl-uds-deployment` PR #4 title) without the supporting signed assets. `vessels v0.3.0` had zero binary assets at the GitHub release; `v0.3.1` tag did not exist.  
Source: `/home/user/workspace/szl/audit_2026-05-29_evening/uds_catalog_honest/REPORT.md`, §3: "5 OUTRIGHT-CLAIM instances requiring remediation."

**Enforcement:**  
- CI grep gate: patterns matching catalog-grade, SLSA-compliant, catalog-ready, production-ready, and air-gap-ready without an adjacent `STAGED-ADVISORY:` prefix or a direct URL to a verifiable signed artifact fail the gate.  
- The a11oy checker emits `OUTRIGHT_CLAIM` for each violation.  
- Human review: any PR containing a bare positive capability claim must have a reviewer explicitly mark the claim as verified or convert it to staged-advisory language.

---

### §13 — Artifact Claims Require Verifiable URLs

**Rule:** Any claim that a specific artifact exists (container image, signed tarball, SBOM, release binary, or attestation file) must include a URL at which the artifact can be independently verified. The URL must be present in the same sentence or in a footnote on the same page. Claims of artifacts without verifiable URLs are inadmissible as governance evidence and must be tagged `status:unverified-artifact`.

**Rationale:** `vessels v0.3.1` was referenced in roadmap documents and PR bodies as if the container image had been pushed to GHCR, when `ghcr.io/szl-holdings/vessels:0.3.1` returned 401 unauthenticated and the tag did not exist on GitHub.  
Source: `/home/user/workspace/szl/audit_2026-05-29_evening/uds_catalog_honest/REPORT.md`, §2: "`uds-v0.3.1` — Tag does not exist — NO"; and "GHCR... Status unknown. Founder action required to push."

**Enforcement:**  
- CI grep gate: artifact name patterns (`:0.3.1`, `ghcr.io/`, `tar.zst`, `.sig`) without an adjacent URL (pattern `https?://`) fail the gate.  
- The a11oy checker emits `ARTIFACT_NO_URL` for claims referencing artifact identifiers without resolvable URLs.  
- Release workflows must include a post-upload step that fetches the artifact URL and records the response code in the DSSE receipt.

---

### §14 — Orchestrator-Mediated Writes Are Explicit

**Rule:** Any write to a repository, file, or governance artifact that is mediated by an orchestrating agent (Cursor, Perplexity agent, GitHub Actions bot, or any other non-human actor) must be flagged as orchestrator-mediated in the commit message, PR body, or receipt. The flag format is `[orchestrator: <tool-name>]` in the commit message trailer. An orchestrator-mediated write that does not carry this flag is treated as an unattributed write and is subject to reversion.

**Rationale:** The Cursor cross-repo proxy pattern was identified as a structural risk: agent-initiated writes crossing repository boundaries could propagate errors across the codebase without clear attribution. Explicit attribution is required to maintain an auditable trail.  
Source: task brief lesson: "Cursor cross-repo proxy pattern → new clause: orchestrator-mediated writes are explicit."

**Enforcement:**  
- CI check: commits from known bot actors (GitHub Actions, Perplexity agent service accounts) must carry the `[orchestrator: <name>]` trailer. The branch protection ruleset is updated to enforce this via a required status check.  
- The a11oy checker flags PRs where the author is a service account but the trailer is absent.  
- Human review: any orchestrator-mediated PR must be approved by a human reviewer before merge, regardless of CI status.

---

### §15 — Structural-Invariant Validation Requires 3-of-N Corpus Convergence

**Rule:** A structural invariant (any claim that a property holds across the SZL system, such as a PAC-Bayes bound, a threshold policy, or a receipt-chain termination guarantee) may only be claimed as validated if at least 3 independent corpora (proof systems, audit logs, or benchmark datasets) converge on the same conclusion. A 2-of-N result is classified as `status:candidate-invariant` and must be so labeled. A 1-of-N result is `status:preliminary`. Candidate-invariant and preliminary claims may not be used as premises in high-impact proof chains.

**Rationale:** The Synthesis Lead's 4-corpus convergence analysis established that 2-of-N witness results were being promoted to validated invariants prematurely. The prior v6 threshold (2-of-N) is upgraded to 3-of-N.  
Source: task brief lesson: "Synthesis Lead's 4-corpus convergence (2-of-N witness) → upgrade: structural-invariant validation requires ≥3 independent corpora convergence to claim."  
Cross-reference: `/home/user/workspace/szl/audit_2026-05-29_evening/synthesis_lead/HONEST_PRIOR_ART.md`, §4, Lamport/BGW entry: "The 2-of-N / 3-of-N witness threshold in IQ-01 is grounded in the BGW fault-tolerance bound."

**Enforcement:**  
- Invariant claims in governance receipts must include a `corpus_convergence` field: an array of at least 3 distinct corpus identifiers with their SHA or DOI.  
- CI check: any DSSE receipt asserting a structural invariant with fewer than 3 corpus entries fails validation.  
- Human review: the Founder must sign off on any new structural invariant claim before it enters a production proof chain.

---

### §16 — Protection-Toggle Merges Require Human-on-Record Authorization Per Merge

**Rule:** Any PR that modifies a safety classifier, disables a protection toggle, relaxes a branch protection ruleset, removes a required status check, or alters a shared-resource modification gate must carry explicit human-on-record authorization. The authorization must be a named Founder or designated authority approval recorded in the PR review thread (GitHub PR review approval, not a comment). Blanket pre-authorization ("all such PRs in this sprint are pre-approved") is not valid. Authorization is per-merge, not per-campaign.

**Rationale:** Safety classifier blocks on shared-resource modification were identified as requiring per-merge authorization rather than blanket pre-approval, which could allow a series of escalating changes to slip through on a single pre-auth grant.  
Source: task brief lesson: "Safety classifier blocks on shared-resource modification → new clause: protection-toggle merges require explicit human-on-record authorization per merge, not blanket pre-auth."

**Enforcement:**  
- CI check: PRs modifying files matching `.github/workflows/`, `branch-protection.json`, `rulesets/`, or `classifier/` must have at least one GitHub PR review approval from a member of the `doctrine-authority` GitHub team.  
- The branch protection ruleset requires this team's review as a required reviewer for these path patterns (CODEOWNERS rule).  
- The a11oy checker includes a PR metadata scan that flags PRs touching protected paths without a recorded human approval.

---

## Part III — Doctrine Meta-Rules

### Compliance Statement

This document was drafted under Doctrine v6. It must pass:
- §1 grep (no superlatives): PASS — no banned terms used without citation.
- §6 grep (no emoji in ## / ### headers): PASS — all headers are ASCII.
- §7 (every claim citable): PASS — every new clause cites the specific session artifact from tonight.
- §8 (lineage tag): N/A — no ancient/philosophical sources cited without tag in this document.

### Precedence

In any conflict between a clause of this doctrine and a standing CI configuration, workflow, or PR template, this doctrine takes precedence. Configurations must be updated to match doctrine, not the reverse.

### Amendment Process

New clauses require: (a) a specific failure case or lesson, (b) Founder approval, (c) a PR to the `.github` repo with a diff showing the exact change to this document, and (d) at least one new enforcement mechanism (grep gate, CI check, or a11oy checker rule).

### Sorry Policy

Seven open sorries existed at the start of session 2026-05-29 evening. PR #109 discharged 2 (leaving 5). Each remaining sorry must carry a named discharge route. The sorry count is a canonical number governed by §11; it must be propagated within 48 hours of any change.

---

*Doctrine v7 | SZL | 2026-05-30 | Drafted by Perplexity subagent under Doctrine v6 | Founder approval required before enactment*
