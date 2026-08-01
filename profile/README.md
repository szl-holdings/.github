<!-- markdownlint-disable MD013 MD033 MD041 -->
<!--
  SZL Holdings organization profile.
  Investor path first; builder and verification paths remain one click away.
  Canonical claims: exactly 8 locked-proven formulas; Lambda uniqueness is
  Conjecture 1; SLSA L1 honest, L2 build-attested, L3 roadmap.
-->

<div align="center">

<img src="./assets/png/szl-holdings-logo.png" alt="SZL Holdings — governed, attributed, executable" width="760" />

# Governed AI that leaves evidence

SZL Holdings builds decision infrastructure for high-consequence AI. The
system can evaluate policy, execute an allowed action, and return a portable
receipt that another party can verify.

[**See the platform**](https://a-11-oy.com) ·
[**Start building**](https://holdings.a-11-oy.com/docs-site/) ·
[**Verify evidence**](https://a11oy.net) ·
[**Explore models and data**](https://huggingface.co/SZLHOLDINGS)

</div>

---

## One substrate, two product lines

| Product | For | Outcome | Explore |
| --- | --- | --- | --- |
| **a11oy** | Enterprises and regulated teams | Governed inference and agentic execution with inspectable decision receipts | [Product](https://a-11-oy.com) · [Source](https://github.com/szl-holdings/a11oy) · [Proof registry](https://a11oy.net) |
| **killinchu** | Defense and maritime operators | A counter-UAS and maritime command demonstration built on the same governance substrate | [Live demo](https://szlholdings-killinchu.hf.space/elite) · [Source](https://github.com/szl-holdings/killinchu) |

The product experience and the evidence experience are intentionally
separate. Product surfaces explain what the system does. Proof surfaces let
reviewers inspect what actually happened.

## The operating thesis

```text
request -> policy gate -> bounded execution -> decision receipt -> independent verification
```

Most AI systems stop at an answer. SZL adds a control and evidence layer:

1. **Attribute the request.** Bind an actor, intent, policy, and source
   revision.
2. **Gate the decision.** Refuse when authority or evidence is insufficient.
3. **Execute within a bound.** Preserve explicit permissions, limits, and
   failure states.
4. **Return evidence.** Emit a receipt that can be retained, replayed, and
   verified outside the product UI.

## Diligence in five links

| Question | Canonical source |
| --- | --- |
| What can I see working? | [a11oy](https://a-11-oy.com) and the [killinchu demonstration](https://szlholdings-killinchu.hf.space/elite) |
| How is the system assembled? | [Platform](https://github.com/szl-holdings/platform) and [a11oy architecture](https://github.com/szl-holdings/a11oy/blob/main/docs/architecture.md) |
| What can be independently checked? | [Proof registry](https://a11oy.net), [receipt specification](https://github.com/szl-holdings/governed-receipt-spec), and [maintained trust documentation](https://github.com/szl-holdings/docs-site/tree/main/docs/trust) |
| What is formally established? | [Lean sources](https://github.com/szl-holdings/lutar-lean) and the [formula ledger](https://github.com/szl-holdings/szl-formula-ledger) |
| Where are the models and data? | [SZLHOLDINGS on Hugging Face](https://huggingface.co/SZLHOLDINGS) and the [receipt lake](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake) |

At canonical Lean revision
[`675d62b`](https://github.com/szl-holdings/lutar-lean/blob/675d62bd6f035047283fd3798440edad049635c2/README.md#tier-1--locked-proven-sorry-free-count-machine-enforced),
observed 2026-08-01, the corpus machine-enforces exactly eight locked-proven
formulas. Lambda uniqueness remains **Conjecture 1**, not a theorem. Runtime
availability, model quality, formal proof, and supply-chain assurance are
different claims and are evaluated at their owning sources.

## Build with SZL

Choose the shortest path for the job:

- **Integrate the platform:** begin in the
  [documentation hub](https://holdings.a-11-oy.com/docs-site/).
- **Verify or emit receipts:** use the
  [governed receipt specification](https://github.com/szl-holdings/governed-receipt-spec)
  and [shared receipt library](https://github.com/szl-holdings/szl-receipt).
- **Add governed tools:** connect through
  [Hatun MCP](https://github.com/szl-holdings/hatun-mcp).
- **Run the shared substrate:** inspect
  [szl-substrate](https://github.com/szl-holdings/szl-substrate) and the
  [platform monorepo](https://github.com/szl-holdings/platform).
- **Read the complete documentation:** open the
  [documentation site](https://holdings.a-11-oy.com/docs-site/).

Every repository should state its audience, maturity, five-minute path,
architecture boundary, evidence level, security policy, and support route.
The shared contract is documented in the
[public experience standard](https://github.com/szl-holdings/.github/blob/main/docs/PUBLIC_EXPERIENCE_STANDARD.md).

## Open-source map

| Layer | Canonical repositories |
| --- | --- |
| **Products** | [a11oy](https://github.com/szl-holdings/a11oy) · [killinchu](https://github.com/szl-holdings/killinchu) |
| **Applications and demonstrations** | [SDA](https://github.com/szl-holdings/sda) · [David Leads](https://github.com/szl-holdings/david-leads) · [IMMUNE](https://github.com/szl-holdings/immune) |
| **Runtime** | [platform](https://github.com/szl-holdings/platform) · [szl-substrate](https://github.com/szl-holdings/szl-substrate) · [Ouroboros](https://github.com/szl-holdings/ouroboros) · [router](https://github.com/szl-holdings/szl-router) |
| **Evidence** | [receipt spec](https://github.com/szl-holdings/governed-receipt-spec) · [receipt library](https://github.com/szl-holdings/szl-receipt) · [trust documentation](https://github.com/szl-holdings/docs-site/tree/main/docs/trust) · [evidence doctrine](https://github.com/szl-holdings/evidence-doctrine) |
| **Formal methods** | [lutar-lean](https://github.com/szl-holdings/lutar-lean) · [formula ledger](https://github.com/szl-holdings/szl-formula-ledger) · [Lambda gate](https://github.com/szl-holdings/szl-lambda-gate) |
| **Models and compute** | [Forge](https://github.com/szl-holdings/szl-forge) · [kernels](https://github.com/szl-holdings/szl-kernels) · [energy attestation](https://github.com/szl-holdings/szl-energy-attest) |
| **Research and examples** | [papers](https://github.com/szl-holdings/szl-papers) · [maintained cookbook recipes](https://github.com/szl-holdings/docs-site/tree/main/docs/cookbook/recipes) · [documentation source](https://github.com/szl-holdings/docs-site) |

Archived repositories are preserved as historical evidence. Their active
successors and retention rationale are listed in the
[estate lifecycle map](https://github.com/szl-holdings/.github/blob/main/docs/ESTATE_LIFECYCLE.md).

## Evidence and status language

The same labels appear across product, code, documentation, and model cards.

| Label | Meaning |
| --- | --- |
| **PROVED** | A precisely scoped statement is machine-checked by the named proof artifact. |
| **MEASURED** | Directly observed with a disclosed instrument, time, and context. |
| **REPORTED** | Supplied by an identified upstream source and not independently measured here. |
| **MODELED** | Simulated, projected, or analytically derived; not a production observation. |
| **CONJECTURE** | A formal hypothesis that remains unproved and is never rendered green. |
| **ROADMAP** | Planned work; no operational claim is made. |

Operational status is reported separately as **OPERATIONAL**, **PARTIAL**,
**DEGRADED**, **UNAVAILABLE**, or **HISTORICAL**.

Evidence integrity does not by itself prove model quality, safety, accuracy,
profitability, compliance, or operational availability.

## Trust and responsible use

- Report vulnerabilities through the
  [security policy](https://github.com/szl-holdings/.github/security/policy).
- Review organization-wide expectations in
  [TRUST.md](https://github.com/szl-holdings/.github/blob/main/TRUST.md) and
  [PRIVACY.md](https://github.com/szl-holdings/.github/blob/main/PRIVACY.md).
- Ask technical questions through the
  [support policy](https://github.com/szl-holdings/.github/blob/main/SUPPORT.md).
- Propose a change through the
  [contribution guide](https://github.com/szl-holdings/.github/blob/main/CONTRIBUTING.md).

No production authorization to operate, regulatory approval, or universal
safety guarantee is claimed by this profile.

---

<div align="center">

Governed · attributed · executable · independently verifiable

[a-11-oy.com](https://a-11-oy.com) ·
[a11oy.net](https://a11oy.net) ·
[Documentation](https://holdings.a-11-oy.com/docs-site/) ·
[Hugging Face](https://huggingface.co/SZLHOLDINGS)

</div>
