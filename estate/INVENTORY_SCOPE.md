# Inventory scope declaration (2026-09-11)

Status: **HOLD**. Tracking: [.github#728](https://github.com/szl-holdings/.github/issues/728).

This directory already carries estate alignment. This note does not replace
`https://a11oy.net/public-membership.json` or
`https://a11oy.net/public-inventory.json`. It records why those two public
files, plus a historical estate-upgrade report, cannot be added or compared
as current totals.

## Incomparable predicates

| Snapshot | Observed | Schema | Counts | Kernel treatment |
| --- | --- | --- | --- | --- |
| Public membership | 2026-09-10T03:20:41Z | `szl.public-profile-inventory/v1` | models 46, datasets 35, spaces 21 | counted once as a model repository |
| Public inventory | 2026-08-31T18:59:11Z | `szl.public-hf-inventory/v3` | models 44, datasets 30, spaces 48, collections 21, buckets 1 | `szl-kernels` listed as a model |
| Estate-upgrade report | 2026-07-22T06:34:06Z | `szl.hf-estate-upgrade-report/v1` | models 15, datasets 32, spaces 26, kernels 10 | historical dry-run |

Identical cardinality can hide missing and unexpected assets. These rows are
not the same scope.

## Kernel kind (separate scope)

Unauthenticated `GET https://huggingface.co/api/kernels?author=SZLHOLDINGS`
on 2026-09-11 listed **14** kernel-type repositories. Scope id:
`hf-public-author-kernels/v1`. That number is not a membership count and is
not the July 22 report's 10.

`SZLHOLDINGS/szl-kernels` still also appears in a model search. `SZLHOLDINGS/szl-khipu-kernels`
appeared in the model search and not in the kernels API list. Dual listing is
not deletion authority.

Hugging Face kernels >= 0.14 load only `kernel` repositories. Retained
legacy model-type kernel repositories begin removal 2026-09-13. Stable pin:
`huggingface/kernels@1dc5c9d05683e8a594bb6d7a1ab18318b89e2caa` (`v0.16.1`).

Still HOLD until:

1. same-scope item-level membership enumeration exists,
2. every production-relevant projection is a first-class kernel repository
   with exact main and v1 revisions,
3. legacy model-type loaders fail closed,
4. remote-code trust is an explicit decision.

Do not create a kernel repository by publishing a model repository as a bypass.
