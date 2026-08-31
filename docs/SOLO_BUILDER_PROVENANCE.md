# Native solo-builder provenance

SZL Holdings uses organization-owned branches and a single authorized operator. Commit-trailer enforcement is therefore retired as an admission control.

The replacement control is `.github/workflows/solo-builder-provenance.yml`. It validates the protected base, the exact pull-request head, the current repository-owned head relationship, and the merge-group identity without checking out or executing proposed content.

This change does not weaken the substantive release boundary. The active `forge9-main` ruleset still requires the eight FORGE-9 contexts, staging verification, signed protected-branch commits, linear history, review-thread resolution, and squash-only merge behavior.

A provenance pass is not a build pass. Tests, security analysis, staging, accessibility/performance checks, Lean integrity, and release attestation remain independent evidence.
