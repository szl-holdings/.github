# Metricool Control Plane

## Status

Metricool is an approved **bounded publishing and analytics adapter** for SZL Holdings.
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
- schedule X, LinkedIn, and any later-connected channels within provider constraints;
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
- overwrite an existing scheduled post without preserving its full provider payload.

## Secrets and identifiers

Do not commit Metricool credentials, bearer tokens, session cookies, user IDs, private
reviewer addresses, or provider refresh tokens.

Runtime integrations should resolve the active SZL Holdings brand through a managed
connection or secret-backed environment configuration. Suggested environment names:

- `METRICOOL_BRAND_ID`
- `METRICOOL_API_TOKEN` when a direct API integration is explicitly introduced
- `METRICOOL_TIMEZONE` with `America/New_York` as the expected SZL default

No secret value belongs in this repository.

## Publication contract

Before a technical claim is scheduled:

1. Bind the claim to current source/evidence.
2. Classify it as verified, observed, inferred, planned, or unobserved.
3. Preserve qualifiers and known limits.
4. Reject or hold the post if the evidence is stale or contradictory.
5. Record the scheduled provider set and publication time.
6. After publication, analytics are observational evidence only; engagement does not
   prove technical correctness.

## Connected-network behavior

The adapter must treat network availability as dynamic. A network is writable only
when the active Metricool brand reports that connection as present and the provider
accepts the post payload.

Provider-specific requirements remain authoritative, including media requirements,
AI-generated-content declarations, review flows, and platform-specific post types.

## Failure semantics

Use explicit states:

- `READY` — active brand resolved and requested provider connected.
- `HOLD` — provider not connected, required media missing, review required, or
  evidence for the public claim is insufficient.
- `UNOBSERVED` — the integration cannot read or verify the requested provider state.
- `FAILED` — Metricool/provider rejected a bounded operation.

Never infer successful publication from successful scheduling alone.

## Change control

Any future direct GitHub-to-Metricool publisher must:

- use least-privilege credentials;
- keep credentials in provider/GitHub secret storage, never source;
- use explicit egress allowlisting for Metricool endpoints;
- emit immutable publication receipts containing source revision, content digest,
  provider, scheduled time, resulting provider/post identifier, and final state;
- preserve protected-main and existing review/security gates;
- ship through a normal feature branch and pull request.
