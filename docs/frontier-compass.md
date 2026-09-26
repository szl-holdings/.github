# Frontier Compass

`szl_frontier_compass.py` is a company-level, read-only audit of the public surfaces
(`a-11-oy.com`, `a11oy.net`, GitHub `szl-holdings`, Hugging Face `SZLHOLDINGS`). Stdlib only.
It runs nightly in `.github/workflows/frontier-compass.yml`; the board memo lands in the job summary.

| Check | What it measures |
|---|---|
| Claims | Every numeric public claim, classified against `.github/data/lean_numbers.json` and the measured public estate: `CANONICAL`, `CURRENT`, `CONSENSUS`, `SCOPED`, `NEGATED`, `HISTORICAL` are fine; `UNEXPLAINED`, `DISSENT`, `STALE` become findings. |
| Lean reproduction | Re-counts the **locked** `lutar-lean` commit with the canonical `lean_numbers.py` method and reports whether the published headline figures reproduce, plus main-HEAD drift. Λ stays Conjecture 1. |
| Freshness | Newest dated snapshot per page older than `--stale-days` (history pages exempt). |
| Links | Dead internal pages (with referrers), links to private / missing / archived repos, HF repo links probed one by one, Space hosts probed. |
| Provenance | Served landing vs the canonical GitHub bytes; only edge injections count as declared deltas. |
| Web + DNS | HSTS strength, CSP scope, HTTP→HTTPS first hop, RFC 9116 `security.txt`, SPF / DMARC (`p=`, not `sp=`) / CAA / DNSSEC for web **and** mail domains. A failed lookup is `UNAVAILABLE`, never "absent". |
| Narrative | No-JS placeholder text nodes, readability, whole-word jargon density, words before the first call to action. |
| Coverage | Every cap and every unverifiable probe is reported. Nothing is silently truncated. |

## Run locally

```bash
GITHUB_TOKEN=$(gh auth token) python -X utf8 tools/compass/szl_frontier_compass.py --out compass-out --fail-on none
python -m pytest -q tools/compass/test_szl_frontier_compass.py
```

Outputs: `compass_report.json`, `BOARD_MEMO.md`, `WORK_ORDERS.md` (stable fingerprints per finding),
and `--baseline <previous compass_report.json>` adds a new/resolved diff.

## Writes (off by default)

`--file-issues` files grouped P0/P1 work orders in `szl-holdings/.github` only when
`SZL_COMPASS_CONFIRM=FILE_WORK_ORDERS` is set and a token is present. Filing is idempotent (fingerprint search,
fail-closed on search errors), capped (`--issue-cap`, max 50), excludes web/DNS posture unless
`--issues-include-security`, neutralises @-mentions, and appends one receipt line per write. CI never files.

Every result is `UNSIGNED_HONEST`: a hash-chained receipt root over the findings, not a signature.
