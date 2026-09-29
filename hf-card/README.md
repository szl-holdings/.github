# hf-card: one card template, one schema, one linter

`hf-card/` is the shared Hugging Face card toolkit for `SZLHOLDINGS` assets.
Each asset's source repository commits a small vars file. `render.py` turns it
into the Hub `README.md` with a single template, and `lint.py` checks any card,
rendered or hand-written, against the same contract.

| File | Role |
| --- | --- |
| `template.md.j2` | One Jinja template with a block per repo type: model, dataset, space, kernel |
| `schema.json` | Required front matter per type (JSON Schema subset) |
| `render.py` | Validates a vars file, renders the card, lints the result, and writes or checks it |
| `lint.py` | Checks front matter against the schema and applies decision D10 |
| `requirements.txt` | Hash-locked runtime closure (Jinja2, MarkupSafe, PyYAML) |
| `tests/` | Network-free tests and one vars fixture per type |

Nothing here contacts the network or the Hub. Writing a card to the Hub stays
the job of the source repository's committed mirror workflow (decision D1).

## The contract

**Front matter.** Every card needs `license`, `tags` and an `szl` mapping with
`source_repo` (`szl-holdings/<repo>`, the one repository that writes the asset)
and `proof_url`. Per type:

- **model:** `library_name`. `base_model` is required when `base_model_relation` is declared.
- **dataset:** nothing extra. `pretty_name`, `task_categories` and `size_categories` are checked when present.
- **space:** `title` and `sdk`. A Docker Space names `app_port`. A Gradio or Streamlit Space names `sdk_version`. `short_description` is at most 60 characters.
- **kernel:** `library_name: kernels`.

`license: other` also needs `license_name` and `license_link`. The toolkit
never supplies a license: a card without one fails. Other keys under `szl`
(for example `artifact_class` or `weights`) are left alone.

**Claims (decision D10).** A card may print the `MEASURED` label, or a
benchmark-style number (a percentage, a latency, a throughput, a speed-up, or a
named metric such as accuracy or F1 followed by a value), only when the same
claim unit links a receipt. A claim unit is one table row, one list item, one
paragraph, one heading, or one front-matter mapping. A receipt link is pinned to
a commit in the card's source repository:

```text
https://github.com/szl-holdings/<repo>/blob/<40-hex sha>/<path>
```

`tree/<sha>/` and `raw.githubusercontent.com/szl-holdings/<repo>/<sha>/` forms
also count. A link to `main`, to another repository, or to the Hub does not.
`model-index` results need `source.url` set to such a link.

These are not claims and are not flagged: a legend that lists three or more
labels (`MEASURED / REPORTED / UNKNOWN`), fenced code, HTML comments, HTML
attributes such as `width="100%"`, and negated figures such as "never 100%".

If a card cannot link a receipt, relabel the claim (for example `REPORTED` or
`UNVERIFIED`) or remove it. The labels follow
[`docs/CLAIM_LANGUAGE.md`](../docs/CLAIM_LANGUAGE.md).

## Use in a source repository

Commit a vars file, for example `hf/card.yaml` (see `tests/fixtures/` for one
per type):

```yaml
type: kernel
repo_id: SZLHOLDINGS/szl-lambda-gate
title: szl-lambda-gate
summary: One paragraph that says what the asset is.
front_matter:
  license: apache-2.0
  library_name: kernels
  tags: [kernel]
  szl:
    source_repo: szl-holdings/szl-lambda-gate
    proof_url: https://github.com/szl-holdings/szl-lambda-gate
claims:
  - label: REPORTED
    claim: Bench file present on the Hub only.
limits:
  - CPU backend only.
```

Render and check it, pinning the toolkit to a reviewed commit of this
repository:

```bash
git clone --filter=blob:none https://github.com/szl-holdings/.github szl-dot-github
git -C szl-dot-github checkout <reviewed sha>
python -m pip install --require-hashes --only-binary=:all: -r szl-dot-github/hf-card/requirements.txt

# keep the committed card equal to the vars file (CI)
python szl-dot-github/hf-card/render.py hf/card.yaml --out README.md --check

# lint any card, rendered or not
python szl-dot-github/hf-card/lint.py README.md --type kernel

# at publish time only: stamp the source commit (decision D4)
python szl-dot-github/hf-card/render.py hf/card.yaml --out .hfstage/README.md --source-sha "$GITHUB_SHA"
```

Leave `--source-sha` out of the committed copy: a file cannot name the commit
that contains it.

## Vars file

| Key | Required | Meaning |
| --- | --- | --- |
| `type` | yes | `model`, `dataset`, `space` or `kernel` |
| `repo_id` | yes | `SZLHOLDINGS/<name>`; the org casing is literal |
| `title`, `summary` | yes | Heading and first paragraph |
| `front_matter` | yes | Emitted as YAML in the order given, then validated against `schema.json` |
| `sections` | no | List of `{heading, body}` markdown sections |
| `claims` | no | List of `{label, claim, receipt}`; `MEASURED` needs `receipt` |
| `limits` | no | List of strings |
| `release` | no | `{tag, source_sha}`; renders the `SZL-HF-MIRROR` release block |
| `dataset`, `space`, `kernel` | no | Type block extras: `structure`; `health_path`, `url`; `backends`, `load` |

Claim labels accepted by `render.py`: `MEASURED`, `REPORTED`, `UNVERIFIED`,
`UNRATIFIED`, `DEGRADED`, `BLOCKED`, `UNAVAILABLE`, `NOT_CLAIMED`.

## Exit codes

| Tool | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `lint.py` | clean | findings | usage or parse error |
| `render.py` | written or up to date | validation, lint or drift failure | usage or schema error |

## Tests

```bash
python -m pip install --require-hashes --only-binary=:all: -r hf-card/requirements.txt
python hf-card/tests/test_hf_card.py
```

The schema validator implements only the keywords `schema.json` uses and fails
closed on any other keyword, so a new rule cannot be added without code that
enforces it.
