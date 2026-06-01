# SZL Holdings — Sovereign Governed AI

**Provable by math, signed by receipts, runs on your hardware.**

[GitHub: szl-holdings](https://github.com/szl-holdings) · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173) · Apache-2.0 OSS

---

## Flagships

Five live organs of the mesh. Each exposes a `/healthz` board reporting the same locked doctrine numbers.

| Module | Space | One line |
|---|---|---|
| **a11oy** | [SZLHOLDINGS/a11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) | Governance gate — Λ-gate router, policy enforcement, MCP host. |
| **amaru** | [SZLHOLDINGS/amaru](https://huggingface.co/spaces/SZLHOLDINGS/amaru) | Memory cortex — hash-linked DSSE receipt chain. |
| **sentra** | [SZLHOLDINGS/sentra](https://huggingface.co/spaces/SZLHOLDINGS/sentra) | Policy immune system — dual-use filter and egress inspection. |
| **rosie** | [SZLHOLDINGS/rosie](https://huggingface.co/spaces/SZLHOLDINGS/rosie) | Operator console — audit-grade copilot across the mesh. |
| **killinchu** | [SZLHOLDINGS/killinchu](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) | Sovereign defense organ — UDS-aware gate for air-gapped deployment. |

## Substrate

Minimal runtime substrate the flagships call. Not products — plumbing.

| Component | Space | Role |
|---|---|---|
| **lean-kernel** | [SZLHOLDINGS/lean-kernel](https://huggingface.co/spaces/SZLHOLDINGS/lean-kernel) | Lean 4 proof kernel — Lutar Invariant Λ. |
| **hatun-mcp** | [SZLHOLDINGS/hatun-mcp](https://huggingface.co/spaces/SZLHOLDINGS/hatun-mcp) | Sovereign MCP tool surface. |
| **status** | [SZLHOLDINGS/status](https://huggingface.co/spaces/SZLHOLDINGS/status) | Live mesh health and `/healthz` board. |

## Coming soon — UDS Edition

| Module | Status | Detail |
|---|---|---|
| **uds-demo** | PRIVATE · Coming Soon · June 16, 2026 | **Warhacker — DoD Pier Demo.** Killinchu UDS edition, UDS-deployable Zarf bundle for air-gapped sovereign deployment. |

<p align="center"><strong>Warhacker T-minus countdown:</strong> June 16–19, 2026 · DoD Pier Demo</p>


> The live JavaScript countdown runs on the [Hugging Face org card](https://huggingface.co/SZLHOLDINGS). The target dates above are authoritative; today the demo is roughly T-15.

---

## Reproducible Evidence

The **Codex-Kernel v1.0.0** release is a replay-grade governed-loop primitive: hash-chained state, decision receipts, an append-only proof ledger, hard-stop validators, and a deterministic replay verifier. It packages everything an independent third party needs to reproduce two bit-exact verified runs (Dresden Venus and SZL governed-ops) on any machine with Node 20+.

**Release:** [platform · v1.0.0-codex-kernel](https://github.com/szl-holdings/platform/releases/tag/v1.0.0-codex-kernel)

| Archive | SHA-256 |
|---|---|
| `codex-kernel-release-v1.0.0.zip` | `6136f3b3ec277a4e4cc8a1157d5afe6633821b29a4133d94a19b843dc9b03f8c` |
| `codex-kernel-release-v1.0.0.tar.gz` | `3ec84df164108795878f5c20f7974d295ab8908513d496e018100c20513a8a13` |

**Verifier one-liner:**

```bash
cd packages/codex-kernel && pnpm install && pnpm tsx src/cli/replay.ts runner/payload.json   # → ATTESTED
```

Aligned with **EU AI Act Article 12** (record-keeping) and **NIST AI RMF**.

---

## What is honest right now

SZL Holdings builds a formally-verified governance gate for agentic AI. The Λ aggregator is proved in Lean 4 (Mathlib v4.13.0) against **749 declarations · 14 unique axioms · 163 tracked sorries**, lutar-lean @ `c7c0ba17`. Every gate decision emits an ECDSA P-256 DSSE-signed receipt onto a hash-linked Khipu Merkle DAG. The stack packages as UDS-deployable Zarf bundles.

- **Λ uniqueness = Conjecture 1** — not a closed theorem.
- **SLSA L1 honest** — real cosign-signed provenance, Sigstore Rekor anchored. SLSA L2 is on the roadmap via Wire D; it is not claimed today.
- **Doctrine v11 LOCKED** — 749 / 14 / 163, locked at `c7c0ba17`.
- Aligned with **EU AI Act Article 12** and **NIST AI RMF (MANAGE)**.

## Open & cited

- **Lean 4** source — [github.com/szl-holdings/lutar-lean](https://github.com/szl-holdings/lutar-lean) @ `c7c0ba17`
- **Concept DOI** [10.5281/zenodo.19944926](https://doi.org/10.5281/zenodo.19944926)
- **Developer hub** — [github.com/szl-holdings/developers](https://github.com/szl-holdings/developers)
- **Compliance posture** — [github.com/szl-holdings/compliance-posture](https://github.com/szl-holdings/compliance-posture). Honest current state: pre-SOC 2 (Type 1 targeted Q4 2026); FedRAMP/IL-4 path targeted Q4 2027.
- Apache-2.0 across all open-source repos.

---

[Founder's personal visualizations →](https://huggingface.co/betterwithage)

---

<sub>Doctrine v11 LOCKED · 🪢 Khipu chain · Lean 4 · Sigstore Rekor · Apache-2.0 OSS · DOI [10.5281/zenodo.19944926](https://doi.org/10.5281/zenodo.19944926) · Source of truth: [szl-holdings/.github lean_numbers.json](https://github.com/szl-holdings/.github/blob/main/.github/data/lean_numbers.json) @ `c7c0ba17` · Founder: Stephen Paul Lutar Jr · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)</sub>
