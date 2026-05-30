# Doctrine v6 to v7 — Change Diff

**Document:** SZL Doctrine upgrade record  
**Prepared:** 2026-05-30  
**Basis:** `/home/user/workspace/szl/audit_2026-05-29_evening/` session artifacts  

---

## Summary of Changes

| Category | v6 | v7 |
|----------|----|----|
| Total clauses | 8 | 16 |
| New clauses | — | 8 (§9–§16) |
| Modified clauses | 0 | 0 |
| Clauses removed | 0 | 0 |
| Witness threshold for invariants | 2-of-N (IQ-01) | 3-of-N (§15) |

---

## Preserved Clauses — No Text Changes

The following 8 clauses are carried verbatim from Doctrine v6. Numbering is assigned (§1–§8); the underlying text is locked.

| v7 ID | v6 text (verbatim) |
|-------|--------------------|
| §1 | No marketing superlatives (revolutionary, unprecedented, world-class, seamless, industry-leading, cutting-edge, game-changing, breakthrough, first, only — unless cited) |
| §2 | No hallucinations / no fake green |
| §3 | No new axioms without prior approval |
| §4 | No new sorries without discharge route |
| §5 | Signed commits (DCO) |
| §6 | No emoji in ## ### headers |
| §7 | Every claim citable |
| §8 | Cultural-reference lineage tag for any ancient/philosophical/esoteric source |

---

## New Clauses — Added in v7

Each new clause is traced to a specific lesson from the 2026-05-29 evening session.

---

### §9 — DOI Dereferencing Required Before Citation

**Lesson:** LIE #5 from HF Truth Audit  
**Failure case:** DOI `10.5281/zenodo.19944926` (concept-DOI alias) was cited and treated as a distinct Zenodo release for several weeks. It resolves to `10.5281/zenodo.20434276`. The distinction between a concept-DOI alias and a version-DOI was not enforced anywhere in the codebase.  
**Session artifact:** `/home/user/workspace/szl/audit_2026-05-29_evening/payload_refresh/ZENODO_GITHUB_MISMATCHES.csv` row 2  
**New rule (condensed):** DOIs must be dereferenced before citation. Concept-DOI aliases must be labeled `[concept-DOI-alias]`. Treating a concept-DOI alias as a fixed release is a violation.

**Diff vs. v6:**
```diff
+ §9 — DOI Dereferencing Required Before Citation
+
+ No DOI may be cited as a distinct work unless it has been dereferenced and confirmed
+ to identify the work being described. Concept-DOI aliases must be explicitly labeled
+ [concept-DOI-alias]. Claiming a concept-DOI alias as a fixed release is a violation.
+
+ Enforcement: CI grep gate on concept-DOI patterns. a11oy checker emits DOI_UNRESOLVED.
```

---

### §10 — Version-Scoped Badge Requirement

**Lesson:** LIE #4 from HF Truth Audit  
**Failure case:** The "Lean Kernel Green" badge in the lutar-lean README was scoped to commit `7ef33a6` but was read (and displayed on 24 HF assets) as implying current-`main` green status. At the time of the audit, `main` build was failing (PRs #98–#102 open).  
**Session artifact:** `/home/user/workspace/szl/audit_2026-05-29_evening/hf_truth_audit/REPORT.md`, LIE #4  
**New rule (condensed):** Every status badge must carry an explicit version anchor (`as of <sha|tag>`). Unscoped badges are fake-green violations under §2 and additionally violate §10.

**Diff vs. v6:**
```diff
+ §10 — Version-Scoped Badge Requirement
+
+ CI badges, status badges, and green-claims must be scoped to a specific commit SHA
+ or semver tag. The anchor must appear in the badge URL or as (as of <sha|tag>)
+ immediately following the badge. Unscoped badges are a violation.
+
+ Enforcement: CI grep gate. a11oy checker emits BADGE_UNSCOPED. badges.json manifest required.
```

---

### §11 — Canonical-Number Propagation Deadline

**Lesson:** LIE #1 from HF Truth Audit  
**Failure case:** The Putnam percentage `8.3% (1/12)` lingered on 31 HF assets after the canonical value was updated to `83.3% (10/12)`. The stale figure was a 10× magnitude error that persisted across investor-facing assets and was never caught by any existing gate.  
**Session artifact:** `/home/user/workspace/szl/audit_2026-05-29_evening/hf_truth_audit/REPORT.md`, LIE #1  
**New rule (condensed):** Canonical numeric values must propagate to all listed files within 48 hours of the canonical update. A canonical-numbers manifest is required. Stale values after 48 hours are violations.

**Diff vs. v6:**
```diff
+ §11 — Canonical-Number Propagation Deadline
+
+ When a canonical numeric is updated, all files in its propagation_targets list must
+ be updated within 48 hours. After 48 hours, a stale numeric is a violation in any
+ file still carrying the old value. canonical_numbers.json is required.
+
+ Enforcement: CI script checks propagation_targets on canonical_numbers.json changes.
+ a11oy checker emits STALE_CANONICAL.
```

---

### §12 — Staged-Advisory Language as Default for Unverified Claims

**Lesson:** UDS catalog-grade outright claims in 5 files  
**Failure case:** Five files contained outright claims of catalog-grade status (`CURSOR_MASTER_DIRECTIVE.md` L562, L587, L594; `UDS_CATALOG_SPONSOR_APPLICATION.md`; `szl-uds-deployment` PR #4 title) without the supporting signed assets. `vessels v0.3.0` had zero binary assets; `v0.3.1` tag did not exist.  
**Session artifact:** `/home/user/workspace/szl/audit_2026-05-29_evening/uds_catalog_honest/REPORT.md`, §3  
**New rule (condensed):** Capability claims not backed by a verifiable signed artifact must carry a `STAGED-ADVISORY:`, `claimed (unverified):`, or `target (not yet achieved):` prefix. Bare positive claims are outright-claim violations.

**Diff vs. v6:**
```diff
+ §12 — Staged-Advisory Language as Default for Unverified Claims
+
+ Capability, status, or readiness claims without a verifiable signed artifact URL
+ must use STAGED-ADVISORY:, claimed (unverified):, or target (not yet achieved):
+ prefix. Bare positive claims are violations.
+
+ Enforcement: CI grep gate on catalog-grade, SLSA-compliant, production-ready without
+ adjacent staged-advisory prefix or artifact URL. a11oy emits OUTRIGHT_CLAIM.
```

---

### §13 — Artifact Claims Require Verifiable URLs

**Lesson:** `vessels v0.3.1` image claimed in roadmap but never pushed  
**Failure case:** `ghcr.io/szl-holdings/vessels:0.3.1` was referenced in roadmap and PR bodies as an existing artifact. The GHCR tag returned 401 unauthenticated; the GitHub tag `uds-v0.3.1` did not exist.  
**Session artifact:** `/home/user/workspace/szl/audit_2026-05-29_evening/uds_catalog_honest/REPORT.md`, §2: "`uds-v0.3.1` — Tag does not exist"  
**New rule (condensed):** Any claim that a specific artifact exists must include a URL at which the artifact can be independently verified. Claims without verifiable URLs are tagged `status:unverified-artifact`.

**Diff vs. v6:**
```diff
+ §13 — Artifact Claims Require Verifiable URLs
+
+ Claims that a specific artifact exists (container image, signed tarball, SBOM,
+ release binary) must include a verifiable URL in the same sentence or footnote.
+ Claims without URLs are status:unverified-artifact violations.
+
+ Enforcement: CI grep gate. a11oy emits ARTIFACT_NO_URL. Release workflows record
+ upload response codes in DSSE receipts.
```

---

### §14 — Orchestrator-Mediated Writes Are Explicit

**Lesson:** Cursor cross-repo proxy pattern  
**Failure case:** Agent-initiated writes crossing repository boundaries lacked explicit attribution, making it impossible to distinguish human-authored commits from orchestrator-generated commits in the audit log without manual investigation.  
**Session artifact:** Task brief lesson: "Cursor cross-repo proxy pattern → orchestrator-mediated writes are explicit"  
**New rule (condensed):** Writes by any non-human actor must carry `[orchestrator: <tool-name>]` in the commit message trailer. Orchestrator-mediated PRs require human reviewer approval before merge.

**Diff vs. v6:**
```diff
+ §14 — Orchestrator-Mediated Writes Are Explicit
+
+ Commits by orchestrating agents must carry [orchestrator: <tool-name>] in the
+ commit message trailer. Orchestrator-mediated PRs require human reviewer approval.
+ Unattributed agent writes are subject to reversion.
+
+ Enforcement: CI check on bot-actor commits. Branch protection requires doctrine-authority
+ team review for orchestrator PRs.
```

---

### §15 — Structural-Invariant Validation Requires 3-of-N Corpus Convergence

**Lesson:** Synthesis Lead's 4-corpus convergence analysis, upgrading from 2-of-N witness  
**Failure case:** The prior v6 threshold (2-of-N corpus witness) was insufficient for promoting results to validated invariants. The Synthesis Lead's 4-corpus analysis demonstrated that 2-of-N convergence had been used to claim invariant status prematurely.  
**Session artifact:** Task brief lesson: "Synthesis Lead's 4-corpus convergence (2-of-N witness) → upgrade: structural-invariant validation requires ≥3 independent corpora convergence to claim"  
Cross-reference: `/home/user/workspace/szl/audit_2026-05-29_evening/synthesis_lead/HONEST_PRIOR_ART.md`, §4  
**New rule (condensed):** Structural invariants require ≥3 independent corpora. 2-of-N = `status:candidate-invariant`. 1-of-N = `status:preliminary`. Neither may serve as premises in high-impact proof chains.

**Diff vs. v6:**
```diff
- IQ-01 witness threshold: 2-of-N corpus convergence sufficient to claim invariant
+ §15 — Structural-Invariant Validation Requires 3-of-N Corpus Convergence
+
+ A structural invariant claim requires ≥3 independent corpora. 2-of-N results are
+ status:candidate-invariant. 1-of-N results are status:preliminary. Neither may
+ serve as proof-chain premises in high-impact contexts.
+
+ Enforcement: DSSE receipt corpus_convergence field must list ≥3 entries. CI receipt
+ validator rejects receipts with fewer than 3. Founder sign-off required for production.
```

---

### §16 — Protection-Toggle Merges Require Human-on-Record Authorization Per Merge

**Lesson:** Safety classifier blocks on shared-resource modification  
**Failure case:** Blanket pre-authorization for protection-toggle modifications (e.g., "all PRs in this sprint that touch classifiers are pre-approved") allows a series of escalating changes to accumulate under a single, under-scrutinized authorization grant.  
**Session artifact:** Task brief lesson: "Safety classifier blocks on shared-resource modification → new clause: protection-toggle merges require explicit human-on-record authorization per merge, not blanket pre-auth"  
**New rule (condensed):** PRs modifying safety classifiers, protection toggles, branch protection rules, or shared-resource modification gates require named human reviewer approval recorded in the PR review thread — per merge, not per campaign.

**Diff vs. v6:**
```diff
+ §16 — Protection-Toggle Merges Require Human-on-Record Authorization Per Merge
+
+ PRs that modify safety classifiers, protection toggles, branch protection rules,
+ or shared-resource modification gates require a named human approval (GitHub PR
+ review, not comment) per merge. Blanket pre-authorization is invalid.
+
+ Enforcement: CODEOWNERS rule for protected paths. doctrine-authority team review
+ required. a11oy PR metadata scan flags missing approvals.
```

---

## Net Effect on Enforcement Surface

| Enforcement type | v6 count | v7 count | Delta |
|-----------------|----------|----------|-------|
| grep CI gates | 3 | 9 | +6 |
| a11oy checker rules | 0 | 8 | +8 |
| CI receipt validators | 1 | 3 | +2 |
| Human review requirements | 2 | 5 | +3 |
| Manifest files required | 0 | 2 (`canonical_numbers.json`, `badges.json`) | +2 |
| CODEOWNERS rules | 0 | 1 (protected paths) | +1 |

---

*Diff prepared 2026-05-30 | Perplexity subagent | Doctrine v6 | For Founder review*
