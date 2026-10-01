# Estate operational source observation

Run the standard-library collector with the existing authenticated `gh` reader:

```text
python .github/scripts/estate_operational_inventory.py --output-dir /path/to/evidence
```

Choose a fresh output directory for every observation. Any existing directory is
refused, including an empty directory, so previous evidence is preserved.

The collector makes bounded GraphQL reads against `github.com`, paginates visible
public organization repositories, records exact default-branch commits and trees,
checks source-local README, license, and SECURITY document presence, and observes
the exact commit's status-check rollup. It rechecks heads and visible membership.
The final census also compares archived state and source commits, closing the
interval after per-batch head rechecks. Validator diagnostics are reduced to
fixed codes and counts; hashes bind their full results without logging text.
Canonical alignment, archive dispositions, and router authority remain in their
existing contracts; this report is a projection, not a replacement manifest.

An optional CSV comparison requires an explicit snapshot observation time:

```text
python .github/scripts/estate_operational_inventory.py --output-dir /path/to/evidence --snapshot-csv /path/to/estate-snapshot.csv --snapshot-observed-at 2026-09-30T02:26:00Z
```

CSV data is unsigned input context. Visibility differences do not prove creation
or deletion. Historical archive dispositions are labelled historical. Unmapped
repositories retain UNKNOWN rather than an invented tier, owner, or successor.

`inventory.json` binds collector and imported validator bytes, canonical authority bytes, optional CSV
bytes, API response commitments, and `inventory.md` bytes. Its `receipt_sha256`
hash covers canonical JSON with that field omitted: sorted keys, compact
separators, UTF-8, and one trailing newline. This is integrity evidence without a
signature. The collector never writes to GitHub or Hugging Face.

`OBSERVED` means the bounded source observation finished and offline canonical
validators passed. It does not mean all organization repositories are visible,
required checks passed, documents are legally sufficient, a merge is allowed,
or a product is published, deployed, ready, or certified. The report explicitly
retains `organization_complete: false`, unknown required checks, and unobserved
readiness. Source-local SECURITY absence does not test inherited org policy.
SECURITY presence is checked in the repository root and `.github` directory.
Unavailable data, moving heads, partial pages, or local contract failures produce
`PARTIAL`, preserved evidence, and a nonzero exit.

```text
python -m unittest discover -s .github/scripts -p test_estate_operational_inventory.py -v
```

The PR workflow runs this offline suite with read-only permissions and pinned
actions. It does not dispatch live inventory or write to a provider.
