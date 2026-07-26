## Satisfies

Satisfies: AT-__ / C-__

## Section reference

Section __ of PAYLOAD FORGE-9

## Root cause

<!-- Explain why it was broken, not only what changed. No shims. -->

## Labels

Labels: <!-- Evidence labels created, changed, or downgraded. -->

## Rollback

Rollback: <!-- Exact command, procedure, or revert SHA. -->

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
- [ ] Commits include a DCO `Signed-off-by:` trailer
- [ ] No force-push, destructive rebase, or safeguard reduction

## Known limitations introduced

<!-- Record limitations before review. Do not leave unresolved placeholders. -->

## Doctrine

- [ ] Doctrine v11 LOCKED 749/14/163 unchanged
- [ ] Sovereign-default preserved; no banned vendors
