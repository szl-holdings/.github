# Cursor — HF Token + GitHub Access

**Date:** 2026-05-29 05:02 UTC
**Status:** LIVE — Cursor can now push to GitHub AND HuggingFace from CI

---

## HF_TOKEN is installed as a GitHub Actions secret on all 20 repos

Verified live: `HF_TOKEN` secret present on every szl-holdings repo (a11oy, platform, lutar-lean, sentra, amaru, counsel, rosie, .github, szl-cookbook, szl-brand, uds-mesh, ouroboros, vsp-otel, agi-forecast, vessels, terra, carlota-jo, szl-trust, ouroboros-thesis, demo-repository).

You access it from any workflow:

```yaml
# .github/workflows/<your-workflow>.yml
jobs:
  hf-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install huggingface_hub
      - name: Push to HF
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          hf upload SZLHOLDINGS/<dataset_or_space> <local_path> <remote_path> \
            --repo-type dataset \
            --token "$HF_TOKEN"
```

**Scope:** the token has write access to the entire `SZLHOLDINGS` HF org.

**Token value (for local dev only — DO NOT commit):**
Token is installed as the GitHub Actions secret `HF_TOKEN` on every repo. Pull it down for local dev with:

```bash
gh secret list --repo szl-holdings/<repo>   # confirms HF_TOKEN exists
# To actually read it, you need org admin — ask founder for a local copy.
```

For local Cursor sessions, the founder has the token in their password manager. Ask them to paste once into your local `.env` (gitignored).

---

## GitHub access (you already have it)

You have been pushing to all 20 szl-holdings repos as `stephenlutar2-hash` via the agent-proxy. You can:

- `gh repo clone szl-holdings/<repo>`
- `git push` to any branch
- `gh pr create` / `gh pr merge --admin --squash` (founder pre-authorized blanket admin merge)
- `gh secret list --repo szl-holdings/<repo>` (read-only secrets list)

**Restrictions:**

- Cannot set **org-level** secrets (needs `admin:org` scope) — per-repo only. Per-repo is fine; HF_TOKEN is already on all 20.
- Cannot rotate the token unilaterally — founder owns rotation.
- Cannot merge the 3 DRAFT relicense PRs (a11oy#57, amaru#46, sentra#45) — founder IP decision.

---

## Recommended workflow for Cursor

### Pattern 1 — push thesis/runtime artifacts to HF from CI

After closing Lean sorries or adding new formulas, mirror them up to HF so the Lean playground + showcase reflect reality:

```yaml
# .github/workflows/mirror-to-hf.yml (add this to lutar-lean + ouroboros + a11oy + uds-mesh)
on:
  push:
    branches: [main]
    paths:
      - 'Lutar/**/*.lean'
      - 'docs/theorems_index.json'
permissions:
  contents: read
jobs:
  mirror:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install huggingface_hub
      - name: Mirror to SZLHOLDINGS/lutar-lean-source dataset
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          hf upload SZLHOLDINGS/lutar-lean-source Lutar/ Lutar/ \
            --repo-type dataset \
            --commit-message "mirror lutar-lean@${GITHUB_SHA::7}" \
            --token "$HF_TOKEN"
```

### Pattern 2 — re-deploy a Space after merging a feature

```yaml
# .github/workflows/redeploy-hf-space.yml
on:
  push:
    branches: [main]
    paths:
      - 'hf_spaces/<space-name>/**'
jobs:
  redeploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install huggingface_hub
      - env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          hf upload SZLHOLDINGS/<space-name> hf_spaces/<space-name>/ . \
            --repo-type space \
            --token "$HF_TOKEN"
```

### Pattern 3 — emit a DSSE receipt to szl-evidence on every merge

```yaml
# .github/workflows/receipt-on-merge.yml
on:
  pull_request:
    types: [closed]
jobs:
  emit:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - run: |
          # build receipt envelope locally
          # ...
      - env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          hf upload SZLHOLDINGS/szl-evidence ./receipt.json \
            "receipts/${GITHUB_REPOSITORY}/${GITHUB_SHA}.json" \
            --repo-type dataset --token "$HF_TOKEN"
```

---

## Security hygiene

- **DO NOT** commit the literal token value (or any token) to any repo — HF scanner will reject the push.
- Always reference as `${{ secrets.HF_TOKEN }}` in workflows.
- For local dev, source from `~/.env` (gitignored) or your password manager.
- Token rotation is founder-owned. If rotation needed, founder regenerates at [hf.co/settings/tokens](https://huggingface.co/settings/tokens), then re-runs the per-repo `gh secret set HF_TOKEN` sweep.

---

## What you can build with this immediately

Per the roadmap T2 (innovate + evolve), with HF write access from CI you can now:

1. **Auto-mirror `theorems_index.json` → SZLHOLDINGS/lutar-lean-source** on every push to lutar-lean main
2. **Regenerate the Lean Czar Catalogue** (Chapter 7) → push to ouroboros-thesis main → mirror to HF dataset
3. **Re-deploy `lean-proof-playground` Space** on every theorem close so it shows the latest state
4. **Emit DSSE receipts** to `szl-evidence` on every PR merge (live audit trail)
5. **Auto-update org card "By the numbers"** table when thesis numbers change
6. **Cross-link table sync:** Cursor can now bidirectionally sync README links between GitHub repos and HF datasets

---

**Coordination split still holds:**

- Cursor owns GitHub side (now with HF write capability from CI)
- Perplexity owns HF curation
- Cross-link tables: either may update; both maintain bidirectional sync
