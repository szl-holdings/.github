# Estate governance scorecard

One fail-closed board covering the `szl-holdings` GitHub organization and the
`SZLHOLDINGS` Hugging Face organization. Runs daily at 07:17 ET with a deeper
Monday sweep, and on demand via `workflow_dispatch`.

## Doctrine labels

Every finding carries exactly one label:

- `MEASURED` - read directly from the GitHub or Hub API this run.
- `REPORTED` - taken from in-repo policy or config, not from a live probe.
- `UNKNOWN` - never probed this run.
- `UNAVAILABLE` - probe attempted, credential or plan cannot see it.

Only `MEASURED` failures turn the run red. The connector credential lacks
`admin:org`, so org-level secrets and code-scanning config legitimately report
`UNAVAILABLE` rather than being scored as green. Use `--strict-unknown` (or the
dispatch input) when you want unresolved controls to block as well.

## What is measured

GitHub, via `.github/scripts/governance_scorecard.py`:

- 2FA requirement, base repository permission, public-repo creation policy,
  web commit signoff, secret-scanning push-protection default.
- Actions allowed-actions policy, default `GITHUB_TOKEN` permission, whether
  the token may approve pull requests.
- Default-branch posture on the most recently pushed repos: required signatures,
  at least one required check or an equivalent ruleset, force-push blocked.
- Supply chain: every `uses:` reference in every readable workflow must be a
  full 40-character commit SHA. Local `./` and `docker://` refs are exempt.
- Public hygiene: license and description present on public repos.

Hugging Face, via `.github/scripts/hf_space_prober.py`:

- Space runtime stage per asset; a public Space that is not `RUNNING` is drift.
- Visibility, gating, declared license.
- Governance stamp presence and a literal model-ID or source backlink in the card.

## Outputs

- `reports/governance/github-scorecard.json` - schema `szl.governance.scorecard/v1`.
- `reports/governance/hf-spaces.json` - schema `szl.governance.hf_probe/v1`.
- Markdown twins rendered into the run summary and uploaded as a 90-day artifact.
- A single rolling issue titled `[governance] estate security drift`, commented
  on rather than duplicated.

Both payloads carry `receipt_state: UNSIGNED_HONEST` until the DSSE lane signs.

## Local run

```bash
export SCORECARD_TOKEN=...   # or GITHUB_TOKEN
export HF_ORG_TOKEN=...
python -I -P .github/scripts/hf_space_prober.py --org SZLHOLDINGS
python -I -P .github/scripts/governance_scorecard.py --org szl-holdings --deep-sample 40
```

Both scripts are stdlib-only, take `--dry-run` to suppress non-zero exits, and
never print credential values.
