## Origin
<!-- What changed and why, in one paragraph. Name the issue, payload section, or incident it answers. -->

## Rights
Original work by the solo maintainer (stephenlutar2-hash); Apache-2.0 unless this repository states otherwise. Third-party code is attributed in-file.

## Agents and tools
<!-- Forge (Claude Code) / Replit / Codex / Perplexity Computer / none — and that a human reviewed the diff before merge. -->

## Tests
<!-- Exact commands and results; the detailed table lives under "Tests executed" below. -->

## Security
<!-- Secrets touched: none | Scanners: gitleaks / trivy / CodeQL result | New network effects or permissions, if any. -->

## Rollback
Rollback: <!-- Exact command, procedure, or revert SHA. Squash merge → `git revert <sha>`. -->

## Known limits
<!-- What this PR does not prove or change. A green check is not a deployment; a deployment is not a proof. -->

---

## Satisfies

Satisfies: AT-__ / C-__

## Section reference

Section __ of PAYLOAD FORGE-9

## Root cause

<!-- Explain why it was broken, not only what changed. No shims. -->

## Labels

Labels: <!-- Evidence labels created, changed, or downgraded. -->

## Risk class

Risk: <A|B|C|D> — reason:

## Tests executed

| Test | Command | Result | Evidence |
| --- | --- | --- | --- |
| | | | |

## Evidence checklist

- [ ] `gate/ground-truth` green
- [ ] `gate/labels` green; no silent evidence promotion
- [ ] `gate/schema` green
- [ ] `gate/adversarial` green
- [ ] `gate/verify-all` green with declared expected failures
- [ ] `gate/provenance` green; attestation verifies
- [ ] `gate/a11y-perf` green at desktop and mobile widths
- [ ] `gate/lean` green; sorry count did not increase
- [ ] Screenshots attached for UI changes
- [ ] `KNOWN_LIMITATIONS.md` updated for any downgrade or blocker
- [ ] Exact-head provenance and all required build/security checks are green
- [ ] No force-push, destructive rebase, or safeguard reduction

## Known limitations introduced

<!-- Record limitations before review. Do not leave unresolved placeholders. -->

## Doctrine

- [ ] Doctrine v11 LOCKED 749/14/163 unchanged
- [ ] Sovereign-default preserved; no banned vendors
