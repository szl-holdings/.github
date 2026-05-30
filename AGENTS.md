# AGENTS.md

## Cursor Cloud specific instructions

This is an **org-level `.github` governance repository** — it contains no
application code, no package managers, and no build steps. The "product" is
a set of reusable GitHub Actions workflows, markdown documentation, issue/PR
templates, and community health files.

### Linting (the only local checks)

| Tool | Command | What it checks |
|---|---|---|
| `markdownlint-cli2` | `markdownlint-cli2 "**/*.md"` | All 15+ markdown files (mirrors CI job in `.github/workflows/ci.yml`) |
| `actionlint` | `actionlint` | All GitHub Actions workflow YAML files in `.github/workflows/` |

- The CI workflow runs `markdownlint-cli2` with `continue-on-error: true`,
  so lint findings do **not** block merges. The existing codebase has ~400
  findings (mostly line-length and indentation).
- `actionlint` passes clean (0 errors) on all 15 workflow files.

### There is no build / run / test step

- No `package.json`, `requirements.txt`, `Makefile`, or any dependency manifest exists.
- No services to start. No database. No backend / frontend.
- Reusable workflows (`.github/workflows/reusable-*.yml`) are consumed by
  other repos via `uses:` and run on GitHub Actions, not locally.

### Conventions

- Conventional Commits required (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`, `refactor:`, `test:`).
- Squash-merge into `main`.
- All Actions must be SHA-pinned (enforced by `pin-check.yml`).
- DCO sign-off required on all commits (`git commit -s`).
