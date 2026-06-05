# SZL Holdings

**Governed-AI decision infrastructure.** Every AI decision becomes a cryptographically signed, replayable, tamper-evident receipt — accountability that no observability or AI-security leader currently ships.

## Two surfaces, one platform

| Surface | What it is | Open |
|---|---|---|
| **a11oy — Command Platform** | One pane of glass: ask & act, safety gates, trust scoring, live decisions, readiness, compliance, forecasting, signed receipts, proof status, threat library, model routing. | [Open](https://szlholdings-a11oy.hf.space/) |
| **Drones & Vessels** | Autonomous-systems field tool: live track board, sensor fusion, maritime picture (sanctions + dark-vessel detection), engagement rules, and verify-it-yourself signed receipts — for air and sea. | [Open](https://szlholdings-killinchu.hf.space/elite) |

The command platform runs every Warhacker challenge problem end to end, and governs the field tool with the same trust scoring, consensus, and signed receipts.

## Verify it yourself
Decisions on the Drones & Vessels surface are signed with a real ECDSA-P256 key. Verify a receipt offline, trusting nothing:
```
curl -s https://szlholdings-killinchu.hf.space/cosign.pub -o cosign.pub
curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/receipt/export
# verify the signature offline -> "Verified OK"; tamper one byte -> "Verification failure"
```

## What we claim — and what we don't
- The trust score is a **research conjecture**, not a proven-unique function. We say so on the platform.
- **5 formulas** are formally proven in Lean (machine-checked, no gaps); the rest are open or experimental.
- **SLSA Build L2** on all service images (cosign + slsa.dev/provenance/v0.2 attestation). **NOT** L3 / FedRAMP / Iron Bank / CMMC.
- Receipts are genuinely signed where a key is present, honestly marked unsigned otherwise — never fabricated.
- Maritime AIS uses a clearly-labeled sample/replay dataset, not a live feed.

## Deploy
```
uds deploy oci://ghcr.io/szl-holdings/szl-mesh:0.4.0 --confirm
```

Built by **Stephen P. Lutar Jr.** · Honest by design · Counsel-governed.
