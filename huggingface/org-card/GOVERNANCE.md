# Governance stamp — SZLHOLDINGS/README

tier: ORG_CARD
state: GOVERNED_PUBLICATION_CONTRACT
source_repository: https://github.com/szl-holdings/.github
manifest: https://github.com/szl-holdings/.github/blob/main/huggingface/org-card.manifest.json
live_receipt: deployment.json
governance: https://github.com/szl-holdings/governance-as-code
verifier: https://github.com/szl-holdings/governed-receipt-spec/blob/main/verify.py

## Claim boundary

This file declares the publication authority and verification path. It does not, by itself, prove that the Space is current, that a model is accurate, or that any runtime is production-ready. Current deployment status is established only when `deployment.json` is served from the public Space and its source revision matches protected `szl-holdings/.github` main.

## Receipt verification

The verifier of record is the [offline Python verifier](https://github.com/szl-holdings/governed-receipt-spec/blob/main/README.md#verify-in-one-command) in `szl-holdings/governed-receipt-spec`. From that repository, install its pinned requirements and run:

```bash
pip install -r requirements.txt
python verify.py examples/a11oy-khipu-chain.json
python verify.py --verify-key tests/fixtures/cosign.pub examples/a11oy-khipu-chain.json
```

Without `--verify-key`, signatures are `SKIP`; a `PASS` means integrity-only, not authenticated signatures. With a supplied key, a successful check verifies envelope signatures against that key, but does not establish signer trust or authorization, re-derive the runtime's internal digest, or qualify a deployed browser consumer. The public `SZLHOLDINGS/governed-receipt-verifier` Space is not a verified receipt-verification path.

## Inference flagship binding

The organization card showcases **SZL Router** as the inference flagship under a separate source and deployment chain:

```text
GitHub source:      szl-holdings/szl-router
Hugging Face mirror: SZLHOLDINGS/llm-router-live
Product integration: https://a-11-oy.com/code
Proof origin:        https://a11oy.net
```

The router repository owns the OpenAI-compatible gateway, logical routing, bounded provider traversal, and per-answer receipt implementation. A11oy owns the integrated product and governance view. The Hugging Face Space is a public status and evidence surface, not the credential-bearing gateway deployment.

A public or running Space does not prove that provider-backed inference is configured. Model and provider availability remain environment-bound and must be reported as `UNAVAILABLE`, `CONFIGURED_UNVERIFIED`, or measured through a bounded receipt-producing probe.

## Catalog references

The following literal IDs are retained for Hub backlinking. Inclusion proves neither availability nor performance:

- SZLHOLDINGS/llm-router-live
- SZLHOLDINGS/SZL-Khipu-1.5B
- SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent
- SZLHOLDINGS/A11OY-MINI
- SZLHOLDINGS/chaski
- SZLHOLDINGS/szl-receiptagent-qwen35-0.8b-v3

Verification proves integrity and origin within its stated scope, never accuracy, performance, compliance, or autonomous authority.
