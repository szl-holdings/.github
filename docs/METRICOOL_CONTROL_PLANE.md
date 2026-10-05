# Metricool Control Plane

## Status

Metricool is a **bounded publishing and analytics adapter** for SZL Holdings.
This source contract is DECLARED; it does not grant live write authority.
It is not a source of truth for product, release, runtime, security, research, or
governance state.

The authority chain remains:

1. GitHub — source and admitted change authority
2. Hugging Face — governed artifact/runtime projection where applicable
3. a-11-oy.com — product/runtime presentation
4. a11oy.net — proofs, receipts, evaluations, and known bounds
5. Metricool — social distribution and channel analytics derived from approved claims

## Purpose

Use Metricool for:

- reading connected-brand settings and channel availability;
- reading scheduled-post state;
- scheduling or updating approved social posts;
- routing posts through review when required;
- reading network analytics and best-time recommendations;
- measuring distribution outcomes without changing upstream technical truth.

## Authority boundary

Metricool MAY:

- distribute already-supported public claims;
- prepare X and LinkedIn drafts only within the committed `approvedChannels`
  allowlist; connecting another network never authorizes it;
- add another channel only after a reviewed change to the committed allowlist;
- read channel analytics and planning state;
- optimize publication timing;
- carry campaign metadata that does not alter technical claims.

Metricool MUST NOT:

- become the canonical source for release or runtime state;
- publish claims of deployment, security closure, model quality, compliance, funding,
  customer adoption, scientific validity, or production readiness unless those claims
  are supported by exact-current upstream evidence;
- store GitHub, Hugging Face, DNS, infrastructure, or unrelated provider credentials;
- silently transform an unverified claim into a verified one;
- bypass human/provider approval requirements;
- overwrite an existing scheduled post without preserving its full provider payload;
- update a post without an atomic conditional write against its observed provider
  revision or updated timestamp; use `HOLD` on mismatch or when equivalent conditional
  writes are unavailable. A read immediately before an unconditional update is insufficient.

Updates additionally require a provider-enforced expected revision (or equivalent
atomic conditional write). A read-then-write comparison alone cannot prevent a
concurrent reviewer edit. The connected update tool has not demonstrated that
primitive; `conditionalUpdatesEnabled` stays false. Do not emulate it with a
local timestamp check or erase provider fields, media, polls, or disclosures.

## Secrets and identifiers

Do not commit Metricool credentials, bearer tokens, session cookies, user IDs, private
reviewer addresses, or provider refresh tokens.

Runtime integrations should resolve the active SZL Holdings brand through a managed
connection or secret-backed environment configuration. Suggested environment names:

- `METRICOOL_BRAND_ID`
- `METRICOOL_API_TOKEN` when a direct API integration is explicitly introduced
- `METRICOOL_TIMEZONE` explicitly set to `America/New_York`; no silent default

No secret value belongs in this repository.

## Publication contract

Before a technical claim is scheduled:

1. Bind the claim to current source/evidence.
2. Use the machine doctrine evidence labels: MEASURED, REPORTED, DECLARED,
   SIMULATED, SAMPLE, MODELED, ROADMAP, UNKNOWN, UNAVAILABLE, BLOCKED.
   Provider operational states are separate from evidence classifications.
3. Preserve qualifiers and known limits.
4. Reject or hold the post if the evidence is stale or contradictory.
5. Record the scheduled provider set and publication time.
6. Bind the schedule to an explicit evidence-validity window ending after the
   intended publication time. Revalidate upstream evidence immediately before delivery.
7. If evidence has changed, expired, or cannot be read, hold or cancel the queued
   publication. If the provider cannot enforce that final check or an equivalent
   cancellation/hold boundary, do not queue the technical claim; use `HOLD`.
8. After publication, analytics are observational evidence only; engagement does not
   prove technical correctness.

Evidence must also be revalidated at delivery, with an enforceable hold/cancel
before publication. A fresh check at scheduling time cannot make future evidence
fresh. That delivery interlock has not been demonstrated in this integration;
`automaticPublicationEnabled` stays false. Existing externally scheduled posts
are not silently adopted, cancelled or relabelled by this contract.

`.github/scripts/metricool_contract.py` implements offline draft preflight only.
It rejects missing, malformed, stale, future-dated, mismatched-source and
mismatched-artifact observations, unauthorized channels, unbound content and
duplicate declared intents. It never returns publication authorization. Inputs
are caller declarations: validating their shape/consistency is not authenticating
their source, semantic truth, human review or signature. A separate trusted
adapter must establish those properties before any future provider mutation.
Never expose this preflight as a live authorization endpoint.

## Connected-network behavior

Network availability is dynamic, but authorization is not inherited from it.
Draft preflight needs an explicit runtime brand ID/timezone, fresh matching
readback, at least one connected approved channel and the committed channel
allowlist. A label alone is insufficient. Adding channels needs reviewed policy.
Brand switching needs an explicit config change and a new readback.
Provider-side connection changes do not expand the committed write scope.

`approvedChannels` is the only configurable channel allowlist and retains the
public names `x` and `linkedin`. The connector/request provider names remain
`twitter` and `linkedin`: fixed code maps `twitter` to channel `x` for the policy
check. Brand connection readbacks, receipts and intent digests retain the wire
provider name. An `x` request is not accepted as a second wire alias. No mapping
grants permission or changes an existing intent identity.

`updatePolicy` and `evidencePolicy` state the required conditional-write and
delivery-evidence safeguards. They do not establish provider support. The
separate implementation flags `conditionalUpdatesEnabled` and
`automaticPublicationEnabled` stay false, so all provider mutations remain
blocked even when a caller claims those capabilities exist.

Provider-specific requirements remain authoritative, including media requirements,
AI-generated-content declarations, review flows, and platform-specific post types.

## Failure semantics

Use the explicit operational states recorded in `publicationStates`:

- `READY` — active brand resolved and an allowlisted requested provider connected;
  this is a precondition, not successful scheduling or delivery.
- `SCHEDULED` — the provider confirms acceptance of a specific post identifier and
  scheduled time; delivery has not yet been observed.
- `PUBLISHED` — provider readback confirms publication of the specific post, with its
  provider/post identifier, delivery timestamp, and evidence/source revision recorded.
  A scheduling response, elapsed time, or engagement metric cannot establish this state.
- `HOLD` — provider not connected, required media missing, review required, or
  evidence for the public claim is insufficient.
- `UNOBSERVED` — the integration cannot read or verify the requested provider state.
- `FAILED` — Metricool/provider rejected a bounded operation.

Never infer successful publication from successful scheduling alone.

These provider operational states are distinct from machine evidence labels and
the offline preflight's `DECLARED`/`BLOCKED` verdict. A passing offline draft
check does not emit READY, SCHEDULED or PUBLISHED, authenticate a provider record,
or authorize an operation. No automatic conversion between these vocabularies
is implemented.

Receipts use separate lifecycle states: `DRAFT`, `SCHEDULED`, `PUBLISHED`,
`BLOCKED`, `UNKNOWN`, `UNAVAILABLE`. `SCHEDULED` is not delivered. `PUBLISHED`
requires provider delivery readback with provider post ID, publication timestamp
and evidence reference; a Metricool planner UUID alone is insufficient. The
receipt schema enforces these fields but does not authenticate them or sign the
receipt. Never mistake JSON Schema validation for provider delivery evidence.

## Offline checks and future adapter boundary

```sh
python .github/scripts/metricool_contract.py
python -m unittest discover -s .github/scripts -p test_metricool_contract.py -v
```

The dedicated PR/merge-queue/push workflow uses pinned Actions and hash-locked
schema dependencies, read-only repository permissions, no provider credentials,
and no provider API calls. The CLI emits only a bounded verdict, never the input
payload or environment. No scheduled provider workflow or second publisher is
introduced.

The intent digest binds the explicit brand, provider, exact UTC scheduled instant,
source revision and entire provider payload (including media/disclosures). Text
normalization is UTF-8, LF line endings and terminal-whitespace removal. Preserve
original text separately. A matching declared planner intent blocks a draft;
this is not atomic deduplication. A future writer needs a durable unique
reservation, recovery after ambiguous outcomes and provider readback before
retry. Unknown outcomes must not trigger blind re-publication.

Read-only analytics may use the provider's supported connector/metric schema.
Store missing metrics as unavailable, not zero. Time-to-post recommendations
need actual dated audience/performance samples. Engagement, clicks and proxy
scores cannot certify technical truth, customers, revenue or investment intent.
The source lists potential interface capabilities, not grants to use them.

## Change control

Any future direct GitHub-to-Metricool publisher must:

- use least-privilege credentials;
- keep credentials in provider/GitHub secret storage, never source;
- use explicit egress allowlisting for Metricool endpoints;
- emit immutable publication receipts containing source revision, content digest,
  provider, scheduled time, resulting provider/post identifier, and final state;
- enforce the committed channel allowlist and revision-conditional update contract;
- revalidate exact upstream evidence before delivery within its recorded validity window;
- preserve protected-main and existing review/security gates;
- ship through a normal feature branch and pull request.
