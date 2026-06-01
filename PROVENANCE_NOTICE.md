# Provenance NOTICE — SLSA L1 honest

> **SLSA L1 honest.** SZL Holdings' verified supply-chain provenance posture is
> **SLSA Level 1 (honest)**: source and build provenance are documented, and
> DSSE/Cosign signing of Khipu receipts is live. **SLSA L2 (hardened
> build-service provenance) is NOT yet attested** — it is a **roadmap item
> delivered via Wire D**. SLSA L3 is not claimed.

## Correction of sibling commit `f59e9f5e`

The commit
[`f59e9f5e`](https://github.com/szl-holdings/.github/commit/f59e9f5e)
("Add SZLHOLDINGS Cosign public key for DSSE Khipu receipt verification") used
the phrase **"SLSA L2 signed provenance"** in its message. **That wording was a
misstatement.** Commit messages are immutable, so this NOTICE is the durable
correction of record:

- The Cosign public key ([`cosign.pub`](cosign.pub)) and DSSE-signed Khipu
  receipts are **real** and verifiable with `cosign verify-blob`.
- Their existence establishes **SLSA L1 (honest)** — documented provenance plus
  signing. It does **not** by itself establish SLSA L2, which additionally
  requires a hardened, isolated build service attesting the build.
- SZL's posture therefore remains **SLSA L1 honest; L2 roadmap via Wire D**.

This NOTICE supersedes any "SLSA L2" phrasing in `f59e9f5e` and aligns the
provenance claim with the honest posture already stated in
[`README.md`](README.md), [`profile/README.md`](profile/README.md), and
[`TRUST.md`](TRUST.md).

---
Signed-off-by: Yachay <yachay@szlholdings.dev>
Doctrine v11 — 749 / 14 / 163 — replay hash c7c0ba17 — SLSA L1 honest.
Co-Authored-By: Perplexity Computer Agent
