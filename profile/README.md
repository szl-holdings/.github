![SZL Holdings evidence lattice](./assets/evidence-lattice-v2.webp)

# SZL Holdings

**AI that signs its work — and refuses to lie.**

Every claim this stack makes carries a cryptographic receipt you can verify yourself. Anything it can't prove, it labels UNAVAILABLE instead of filling in a plausible-looking answer. No silent confidence. No fabricated "LIVE." Just signed evidence and honest bounds.

## See it in 30 seconds

Open **[a-11-oy.com](https://a-11-oy.com)** — the living command fabric. Every governed action emits a hash-chained, DSSE-signed receipt. Don't take our word for it: pull a receipt and verify it against the public contract. That's the whole pitch — you don't have to trust us, you can check.

## Start here

1. **The product** — [a-11-oy.com](https://a-11-oy.com): the A11oy command substrate, live capability status, governed workflows. This is the front door.
2. **The proof** — [a11oy.net](https://a11oy.net): the proof registry. Receipts, evaluations, and known bounds — including the things we *can't* yet prove.
3. **Install the stack** — [PyPI](https://pypi.org/user/betterwithage/): 20 packages, each published with OIDC trusted publishing and build provenance. `pip install szl-guardrail-receipt` and you're holding the receipt machinery.
4. **Browse the artifacts** — [Hugging Face / SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS): models, software kernels, datasets, and Spaces, each with its own evidence and stated limits.
5. **Read the source** — [github.com/szl-holdings](https://github.com/szl-holdings): canonical source, evaluation lanes, and per-repo controls.

## The receipt stack on PyPI

Twenty installable packages that *are* the provenance tooling — not claims about it. Receipt primitives, guardrail and energy witnesses, calibration and retrieval benchmarks, and an OpenTelemetry evidence exporter. Every one is published by OIDC trusted publishing (no stored tokens) with PEP 740 build attestations, and every one fails closed: `MEASURED`, `BLOCKED`, or `UNAVAILABLE`, never coerced.

```bash
pip install szl-receipts szl-guardrail-receipt vsp-otel szl-nemo
```

## The doctrine

Source, running software, and model evaluations are **separate claims**, and we keep them separate. A green test is not a deployment; a deployment is not a proof. Unknowns stay visible. This is the same discipline the industry is now converging on for supply-chain security — SLSA provenance, in-toto, Sigstore — except here it's not a compliance layer bolted on after the fact. It's the product.

## Current state (honest, dated)

Public Hugging Face estate observed **2026-09-30**: **50 models, 35 datasets, 33 Spaces** (repository counts). Twenty PyPI packages published. These are dated observations, refreshed from the live Hub API — not marketing numbers.

**Receipt verification:** the [a11oy source](https://github.com/szl-holdings/a11oy) carries the verification contracts. **Model training and evaluation:** [szl-forge](https://github.com/szl-holdings/szl-forge) holds the kits, datasets, runbooks, and measured limits. **Trust boundary:** [TRUST.md](https://github.com/szl-holdings/.github/blob/main/TRUST.md). Killinchu effectors stay **SIMULATED**; `SZLHOLDINGS/SZLHOLDINGS` is **HISTORICAL**.

*Governed AI. Evidence you can inspect. Work you can verify.*
