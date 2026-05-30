/-
  Lutar / Doctrine / V7.lean
  SZL Doctrine v7 — Formal Compliance Predicate Stubs

  Status: stub layer — all proofs are `sorry`-discharged pending full elaboration.
  Each sorry carries a named discharge route per Doctrine v7 §4.

  This file must compile under:  lake build Lutar.Doctrine.V7
  Lean version target: Lean 4 (leanprover/lean4:v4.8.0)

  Doctrine reference: /home/user/workspace/szl/audit_2026-05-29_evening/doctrine_v7/DOCTRINE_V7.md
  Session: 2026-05-29 evening audit
-/

import Mathlib.Data.List.Basic
import Mathlib.Data.String.Basic
import Mathlib.Data.Finset.Basic

namespace Lutar.Doctrine.V7

-- ---------------------------------------------------------------------------
-- Core types
-- ---------------------------------------------------------------------------

/-- A Header is the text content of a markdown `##` or `###` heading. -/
structure Header where
  level : Nat  -- 2 or 3
  text  : String
  deriving Repr

/-- A Claim is any factual assertion appearing in an SZL artifact. -/
structure Claim where
  text      : String
  citations : List String  -- list of citation URLs or artifact paths
  deriving Repr

/-- A Badge represents a CI status badge in a README or governance artifact. -/
structure Badge where
  url          : String
  versionAnchor : Option String  -- Some "7ef33a6" or None
  deriving Repr

/-- A DOI citation carrying its resolved type. -/
inductive DOIType
  | versionDOI    -- resolves to a specific immutable snapshot
  | conceptDOIAlias  -- resolves to the latest version; NOT a fixed release
  deriving Repr, DecidableEq

structure DOICitation where
  doi      : String
  doiType  : DOIType
  deriving Repr

/-- A CanonicalNumber is a named numeric value with a propagation target list. -/
structure CanonicalNumber where
  key               : String
  value             : String
  propagationTargets : List String  -- file paths that must carry this value
  deriving Repr

/-- A CapabilityClaim is a status or readiness assertion. -/
inductive CapabilityClaimType
  | outright        -- bare positive claim; must have verifiable artifact URL
  | stagedAdvisory  -- correctly prefixed with STAGED-ADVISORY: etc.
  deriving Repr, DecidableEq

structure CapabilityClaim where
  text       : String
  claimType  : CapabilityClaimType
  artifactURL : Option String
  deriving Repr

/-- An ArtifactReference is a claim that a specific artifact exists. -/
structure ArtifactReference where
  identifier  : String  -- e.g. "ghcr.io/szl-holdings/vessels:0.3.1"
  verifiableURL : Option String
  deriving Repr

/-- A CommitRecord tracks authorship and attribution. -/
structure CommitRecord where
  sha              : String
  authorIsHuman    : Bool
  orchestratorTag  : Option String  -- Some "[orchestrator: Cursor]" or None
  deriving Repr

/-- A StructuralInvariantClaim carries its corpus evidence list. -/
structure StructuralInvariantClaim where
  name    : String
  corpora : List String  -- distinct corpus identifiers
  deriving Repr

/-- A ProtectionTogglePR is a PR that modifies a safety classifier or branch protection. -/
structure ProtectionTogglePR where
  prNumber              : Nat
  humanApprovalRecorded : Bool  -- per-merge GitHub PR review approval (not comment)
  deriving Repr

-- ---------------------------------------------------------------------------
-- §1 — No marketing superlatives in any SZL artifact header or prose
-- ---------------------------------------------------------------------------

def superlativeTerms : List String :=
  ["revolutionary", "unprecedented", "world-class", "seamless",
   "industry-leading", "cutting-edge", "game-changing", "breakthrough"]

def containsSuperlative (s : String) : Bool :=
  superlativeTerms.any (fun t => s.toLower.containsSubstr t)

/-- §1 compliance: a header must not contain any banned superlative. -/
theorem no_superlative_in_header (h : Header) (hClean : containsSuperlative h.text = false) :
    ¬ containsSuperlative h.text := by
  -- discharge: `decide` once `containsSuperlative` is fully decidable over the
  -- finite superlativeTerms list and a concrete Header instance.
  -- discharge-route: String.containsSubstr decidability + simp/decide
  simp [containsSuperlative] at hClean
  exact fun hContra => by simp [hContra] at hClean

-- ---------------------------------------------------------------------------
-- §2 — No fake green: badges must be version-scoped (cross-reference §10)
-- ---------------------------------------------------------------------------

/-- §2/§10 compliance: a badge is honest iff it carries a version anchor. -/
def badgeIsVersionScoped (b : Badge) : Bool :=
  b.versionAnchor.isSome

theorem no_fake_green_badge (b : Badge) (hScoped : badgeIsVersionScoped b = true) :
    b.versionAnchor.isSome = true := by
  -- discharge: unfold badgeIsVersionScoped; exact hScoped
  -- discharge-route: definitional unfolding
  unfold badgeIsVersionScoped at hScoped
  exact hScoped

-- ---------------------------------------------------------------------------
-- §6 — No emoji in level-2/level-3 headers
-- ---------------------------------------------------------------------------

/-- Returns true iff the string contains any non-ASCII code point (proxy for emoji). -/
def containsNonAscii (s : String) : Bool :=
  s.any (fun c => c.val > 127)

/-- §6 compliance: a header at level 2 or 3 must not contain non-ASCII characters. -/
theorem no_emoji_in_header (h : Header) (hLevel : h.level = 2 ∨ h.level = 3)
    (hAscii : containsNonAscii h.text = false) :
    ¬ containsNonAscii h.text := by
  -- discharge: simp [hAscii]
  -- discharge-route: definitional; hAscii is the hypothesis directly
  simp [hAscii]

-- ---------------------------------------------------------------------------
-- §7 — Every claim must have at least one citation
-- ---------------------------------------------------------------------------

/-- §7 compliance: a claim is citable iff its citation list is non-empty. -/
def claimIsCitable (c : Claim) : Bool :=
  !c.citations.isEmpty

theorem every_claim_has_citation (c : Claim) (hCite : claimIsCitable c = true) :
    c.citations ≠ [] := by
  -- discharge: unfold claimIsCitable; simp [List.isEmpty_iff_eq_nil] at hCite; exact hCite
  -- discharge-route: List.isEmpty characterisation
  unfold claimIsCitable at hCite
  simp [List.isEmpty] at hCite
  exact hCite

-- ---------------------------------------------------------------------------
-- §9 — DOI Dereferencing: concept-DOI aliases must be labeled
-- ---------------------------------------------------------------------------

/-- A DOI citation is valid iff:
    - version DOIs are used as-is, or
    - concept-DOI aliases are explicitly labeled as such (doiType = conceptDOIAlias). -/
def doiCitationIsValid (d : DOICitation) : Bool :=
  match d.doiType with
  | DOIType.versionDOI      => true
  | DOIType.conceptDOIAlias => true  -- labeled; structurally valid because the label IS the disclosure

/-- §9 compliance: a concept-DOI alias that is explicitly typed as such is not a violation. -/
theorem concept_doi_alias_must_be_labeled
    (d : DOICitation) (hType : d.doiType = DOIType.conceptDOIAlias) :
    doiCitationIsValid d = true := by
  -- discharge: simp [doiCitationIsValid, hType]
  -- discharge-route: definitional case split on doiType
  simp [doiCitationIsValid, hType]

/-- §9 non-compliance: using a concept-DOI alias without the label is a violation.
    We encode "no label" as a citation with doiType = versionDOI but the DOI string
    matching the known alias pattern — this is the runtime gate check. -/
def isKnownConceptAlias (doi : String) : Bool :=
  -- In production: check against the canonical alias registry
  -- Stub: flag the specific alias from tonight's audit
  doi == "10.5281/zenodo.19944926"

theorem known_alias_must_not_be_cited_as_version
    (d : DOICitation) (hAlias : isKnownConceptAlias d.doi = true)
    (hWrongType : d.doiType = DOIType.versionDOI) :
    False := by
  -- discharge: this theorem encodes the violation predicate; runtime gate should reject before this state
  -- discharge-route: add doi to alias registry; gate checks doiType at citation parse time
  sorry
  -- discharge: build alias registry + DOI-type parser in the citation linter

-- ---------------------------------------------------------------------------
-- §10 — Version-Scoped Badge Requirement (see also §2)
-- ---------------------------------------------------------------------------

/-- §10 compliance: all badges in a file must be version-scoped. -/
def allBadgesScoped (badges : List Badge) : Bool :=
  badges.all badgeIsVersionScoped

theorem all_badges_scoped (badges : List Badge) (hAll : allBadgesScoped badges = true) :
    ∀ b ∈ badges, b.versionAnchor.isSome = true := by
  -- discharge: List.all_iff_forall + badgeIsVersionScoped definition
  -- discharge-route: simp [allBadgesScoped, List.all_iff_forall, badgeIsVersionScoped] at hAll; exact hAll
  intro b hb
  simp [allBadgesScoped, List.all_iff_forall] at hAll
  exact hAll b hb |>.symm ▸ rfl
  sorry
  -- discharge: fix the exact simp lemmas for List.all_iff_forall in Mathlib4

-- ---------------------------------------------------------------------------
-- §11 — Canonical-Number Propagation Deadline
-- ---------------------------------------------------------------------------

/-- §11 compliance: a canonical number update is propagated iff all target files
    appear in the set of files updated within the deadline window. -/
def canonicalPropagated (cn : CanonicalNumber) (updatedFiles : Finset String) : Bool :=
  cn.propagationTargets.all (fun path => updatedFiles.contains path)

theorem canonical_propagation_complete
    (cn : CanonicalNumber) (updatedFiles : Finset String)
    (hProp : canonicalPropagated cn updatedFiles = true) :
    ∀ path ∈ cn.propagationTargets, path ∈ updatedFiles := by
  -- discharge: List.all_iff_forall + Finset.mem_def
  -- discharge-route: simp [canonicalPropagated, List.all_iff_forall] at hProp; exact hProp
  intro path hpath
  simp [canonicalPropagated, List.all_iff_forall] at hProp
  exact hProp path hpath
  sorry
  -- discharge: Finset.contains = Finset.mem bridge in Mathlib4

-- ---------------------------------------------------------------------------
-- §12 — Staged-Advisory Language for Unverified Claims
-- ---------------------------------------------------------------------------

/-- §12 compliance: a capability claim is doctrine-compliant iff:
    - it is outright AND has a verifiable artifact URL, OR
    - it is staged-advisory (prefix present). -/
def capabilityClaimCompliant (cc : CapabilityClaim) : Bool :=
  match cc.claimType with
  | CapabilityClaimType.outright       => cc.artifactURL.isSome
  | CapabilityClaimType.stagedAdvisory => true

theorem staged_advisory_always_compliant (cc : CapabilityClaim)
    (hSA : cc.claimType = CapabilityClaimType.stagedAdvisory) :
    capabilityClaimCompliant cc = true := by
  -- discharge: simp [capabilityClaimCompliant, hSA]
  simp [capabilityClaimCompliant, hSA]

theorem outright_claim_requires_url (cc : CapabilityClaim)
    (hOut : cc.claimType = CapabilityClaimType.outright)
    (hNoURL : cc.artifactURL = none) :
    capabilityClaimCompliant cc = false := by
  -- discharge: simp [capabilityClaimCompliant, hOut, hNoURL]
  simp [capabilityClaimCompliant, hOut, hNoURL]

-- ---------------------------------------------------------------------------
-- §13 — Artifact Claims Require Verifiable URLs
-- ---------------------------------------------------------------------------

/-- §13 compliance: an artifact reference is valid iff it has a verifiable URL. -/
def artifactRefValid (ar : ArtifactReference) : Bool :=
  ar.verifiableURL.isSome

theorem artifact_without_url_is_violation (ar : ArtifactReference)
    (hNoURL : ar.verifiableURL = none) :
    artifactRefValid ar = false := by
  -- discharge: simp [artifactRefValid, hNoURL]
  simp [artifactRefValid, hNoURL]

-- ---------------------------------------------------------------------------
-- §14 — Orchestrator-Mediated Writes Are Explicit
-- ---------------------------------------------------------------------------

/-- §14 compliance: a commit by a non-human author must carry an orchestrator tag. -/
def commitAttributionCompliant (cr : CommitRecord) : Bool :=
  if cr.authorIsHuman then true
  else cr.orchestratorTag.isSome

theorem human_commit_always_compliant (cr : CommitRecord) (hHuman : cr.authorIsHuman = true) :
    commitAttributionCompliant cr = true := by
  simp [commitAttributionCompliant, hHuman]

theorem bot_commit_requires_orchestrator_tag (cr : CommitRecord)
    (hBot : cr.authorIsHuman = false)
    (hNoTag : cr.orchestratorTag = none) :
    commitAttributionCompliant cr = false := by
  simp [commitAttributionCompliant, hBot, hNoTag]

-- ---------------------------------------------------------------------------
-- §15 — Structural-Invariant Validation Requires 3-of-N Corpus Convergence
-- ---------------------------------------------------------------------------

/-- §15 compliance: a structural invariant is validated only when ≥3 corpora agree. -/
def invariantIsValidated (sic : StructuralInvariantClaim) : Bool :=
  sic.corpora.length >= 3

def invariantIsCandidateOnly (sic : StructuralInvariantClaim) : Bool :=
  sic.corpora.length = 2

def invariantIsPreliminary (sic : StructuralInvariantClaim) : Bool :=
  sic.corpora.length = 1

theorem fewer_than_three_corpora_not_validated (sic : StructuralInvariantClaim)
    (hLt : sic.corpora.length < 3) :
    invariantIsValidated sic = false := by
  -- discharge: simp [invariantIsValidated]; omega
  simp [invariantIsValidated]
  omega

theorem three_or_more_corpora_validated (sic : StructuralInvariantClaim)
    (hGe : sic.corpora.length >= 3) :
    invariantIsValidated sic = true := by
  simp [invariantIsValidated]
  exact Nat.ble_eq_true_of_le hGe
  sorry
  -- discharge: Nat.ble_eq_true_of_le / decide for concrete cases

-- ---------------------------------------------------------------------------
-- §16 — Protection-Toggle Merges Require Human-on-Record Authorization Per Merge
-- ---------------------------------------------------------------------------

/-- §16 compliance: a protection-toggle PR is compliant iff a human approval is recorded. -/
def protectionToggleCompliant (pr : ProtectionTogglePR) : Bool :=
  pr.humanApprovalRecorded

theorem protection_toggle_without_human_approval_is_violation (pr : ProtectionTogglePR)
    (hNoApproval : pr.humanApprovalRecorded = false) :
    protectionToggleCompliant pr = false := by
  simp [protectionToggleCompliant, hNoApproval]

theorem protection_toggle_with_human_approval_compliant (pr : ProtectionTogglePR)
    (hApproval : pr.humanApprovalRecorded = true) :
    protectionToggleCompliant pr = true := by
  simp [protectionToggleCompliant, hApproval]

-- ---------------------------------------------------------------------------
-- Full-file compliance predicate
-- ---------------------------------------------------------------------------

/-- A DoctrineV7Artifact bundles all checkable artifact components. -/
structure DoctrineV7Artifact where
  headers        : List Header
  claims         : List Claim
  badges         : List Badge
  doiCitations   : List DOICitation
  capClaims      : List CapabilityClaim
  artifactRefs   : List ArtifactReference
  commits        : List CommitRecord
  invariants     : List StructuralInvariantClaim
  protectionPRs  : List ProtectionTogglePR

/-- Full v7 compliance: all sub-predicates must hold. -/
def doctrineV7Compliant (a : DoctrineV7Artifact) : Bool :=
  a.headers.all (fun h => !containsSuperlative h.text) &&
  a.headers.all (fun h => (h.level = 2 ∨ h.level = 3) → !containsNonAscii h.text) &&
  a.claims.all claimIsCitable &&
  a.badges.all badgeIsVersionScoped &&
  a.capClaims.all capabilityClaimCompliant &&
  a.artifactRefs.all artifactRefValid &&
  a.commits.all commitAttributionCompliant &&
  a.invariants.all invariantIsValidated &&
  a.protectionPRs.all protectionToggleCompliant

/-- The empty artifact trivially complies (vacuous truth — used for bootstrapping). -/
theorem empty_artifact_compliant :
    doctrineV7Compliant ⟨[], [], [], [], [], [], [], [], []⟩ = true := by
  simp [doctrineV7Compliant, containsSuperlative, containsNonAscii,
        claimIsCitable, badgeIsVersionScoped, capabilityClaimCompliant,
        artifactRefValid, commitAttributionCompliant,
        invariantIsValidated, protectionToggleCompliant]

end Lutar.Doctrine.V7
