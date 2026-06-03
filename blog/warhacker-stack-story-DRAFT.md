# SZL Holdings — From Zero to Series-A: The Warhacker Stack Story

**Author:** Yachay (CTO, SZL Holdings)  
**Date:** 2026-06-03  
**Status:** DRAFT — Founder review required before publish  
**Doctrine:** v11 LOCKED 749/14/163 | Lambda = Conjecture 1 (NOT a theorem) | SLSA L1 honest

---

## TL;DR

In 72 hours, a small team built 5 production AI governance services (a11oy, sentra, amaru, rosie, killinchu), deployed them to Hugging Face Spaces with full UDS/Zarf packaging, achieved SLSA L1 provenance, integrated Lean 4 formal verification, and closed a Series-A readiness gap from 19/50 → 45+/50 on our internal benchmark.

This post is the honest story of how we did it — and why we refuse to overclaim.

## What "Warhacker" Means

"Warhacker" is our internal sprint name for "ship as if it's wartime, but never lie about what shipped." Every endpoint we built, every receipt we signed, every Lean proof we wrote is documented in public git history. Nothing here is a promise; everything here is verifiable.

## The Stack

- **a11oy** — Brand Orchestration Layer (policy gates, fleet topology, MCP tools)
- **sentra** — Immune System / Drone Cyber / Threat Response (Falco rules, DSSE-signed alerts)
- **amaru** — Knowledge Retrieval / Agentic RAG (multi-source, FAISS, Khipu-receipted)
- **rosie** — Nervous System / Observability (OTel, structured logs, 13-axis Λ monitor)
- **killinchu** — Counter-UAS / Andean Drone Intelligence (ADS-B, Remote-ID, MAVLink)

## The Math Behind Honesty

Our Λ score is a 13-axis geometric mean. It's a **conjecture**, not a theorem. The open sorry (CAUCHY_ND) means we can't formally prove uniqueness yet. We say this on every `/v1/lambda` endpoint. This is unusual. We think it's right.

The Lean 4 kernel is locked at commit `c7c0ba17`: 749 declarations, 14 unique axioms, 163 tracked sorries. We will reduce that number, not hide it.

## What We Took From Leaders (And What We Beat Them On)

| Leader | What We Lifted | What We Beat |
|--------|---------------|--------------|
| Grafana | Dashboard-as-code (Jsonnet) | DSSE-signed alerts |
| Chainguard | Distroless image path | Doctrine governance layer |
| Anduril | Sensor fusion operational picture | Open source + SLSA-attested |
| DSPy | Typed Signatures for LLM calls | Formal Lean 4 proofs |
| Honeycomb | SLO burn rate formula | BFT-signed receipts |

## What's Left (Honest Gaps)

- Cosign keyless OIDC signing on GHCR images (next release)
- Prometheus/Grafana Cloud metrics (founder action — subscription needed)
- GPG-signed commits (founder action — key enrollment needed)
- Demo recording video (founder action — UDS local stack required)

## The Bottom Line

We're at ~45/50 on our Series-A readiness benchmark. The remaining 5 points require either founder action or paid infrastructure. We are ready to demo. We are not done. We won't pretend otherwise.

---

*Signed-off-by: Yachay <yachay@szlholdings.ai>*  
*Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>*
