# GitHub ↔ Hugging Face alignment — recapture 2026-09-04

**Status:** `SOURCE_MIRROR_RECAPTURE_PUBLISHED`  
**Captured:** 2026-09-04T18:55:00Z  
**Evidence class:** MEASURED (counts and HTTP) + REPORTED (classification)  
**Does not rewrite:** `docs/GITHUB_HF_ALIGNMENT.md` (2026-08-29 snapshot) or a11oy-net frozen Hub inventory.

GitHub org [`szl-holdings`](https://github.com/szl-holdings) is protected source.  
Hugging Face org [`SZLHOLDINGS`](https://huggingface.co/SZLHOLDINGS) is the public artifact / runtime mirror.

One product, two IMMUNE URLs. Do not delete Channel A or Channel B.

## Measured this pass

| Surface | Count | Source |
| --- | ---: | --- |
| GitHub public repos listed | 115 | `gh api orgs/szl-holdings` |
| GitHub rows returned | 121 | `gh repo list` (incl. private + archived) |
| GitHub archived | 34 | same |
| GitHub private observed | 6 | same |
| Hub models | 44 | `/api/models?author=SZLHOLDINGS` |
| Hub datasets | 32 | `/api/datasets?author=SZLHOLDINGS` |
| Hub Spaces public API | 15 | `/api/spaces?author=SZLHOLDINGS` |

## Public Spaces (keep)

| Hub Space | GitHub twin | Product / homepage |
| --- | --- | --- |
| [SZLHOLDINGS/immune](https://huggingface.co/spaces/SZLHOLDINGS/immune) | [szl-holdings/immune](https://github.com/szl-holdings/immune) | [a-11-oy.com/immune](https://a-11-oy.com/immune) |
| [SZLHOLDINGS/immune-lattice](https://huggingface.co/spaces/SZLHOLDINGS/immune-lattice) | [szl-holdings/immune](https://github.com/szl-holdings/immune) (canonical). `immune-lattice` repo is ARCHIVED hologram | Channel B COP |
| [SZLHOLDINGS/a11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) | [szl-holdings/a11oy](https://github.com/szl-holdings/a11oy) | [a-11-oy.com](https://a-11-oy.com) |
| [SZLHOLDINGS/killinchu](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) | [szl-holdings/killinchu](https://github.com/szl-holdings/killinchu) | [a-11-oy.com/killinchu](https://a-11-oy.com/killinchu) |
| [SZLHOLDINGS/counsel](https://huggingface.co/spaces/SZLHOLDINGS/counsel) | `counsel` GitHub repo ARCHIVED | Space remains public runtime |
| [SZLHOLDINGS/terra](https://huggingface.co/spaces/SZLHOLDINGS/terra) | vertical-services + szl-real-estate | Space runtime |
| [SZLHOLDINGS/sentra](https://huggingface.co/spaces/SZLHOLDINGS/sentra) | vertical-services | Space runtime |
| [SZLHOLDINGS/finance](https://huggingface.co/spaces/SZLHOLDINGS/finance) | vertical-services + szl-quant | Space runtime |
| [SZLHOLDINGS/lyte](https://huggingface.co/spaces/SZLHOLDINGS/lyte) | [lyte-lattice](https://github.com/szl-holdings/lyte-lattice) | [a-11-oy.com/lyte](https://a-11-oy.com/lyte) |
| [SZLHOLDINGS/vertical-services](https://huggingface.co/spaces/SZLHOLDINGS/vertical-services) | [vertical-services](https://github.com/szl-holdings/vertical-services) | Hub homepage set this pass |
| [SZLHOLDINGS/szl-command-lab](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) | [szl-command-lab](https://github.com/szl-holdings/szl-command-lab) | Hub homepage set this pass |
| [SZLHOLDINGS/david-leads](https://huggingface.co/spaces/SZLHOLDINGS/david-leads) | [david-leads](https://github.com/szl-holdings/david-leads) | already Hub |
| [SZLHOLDINGS/szl-constellation](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | [szl-constellation](https://github.com/szl-holdings/szl-constellation) | Hub homepage set this pass |
| [SZLHOLDINGS/szl-frontier](https://huggingface.co/spaces/SZLHOLDINGS/szl-frontier) | [szl-frontier](https://github.com/szl-holdings/szl-frontier) | already Hub |
| [SZLHOLDINGS/szl-model-inference-lab](https://huggingface.co/spaces/SZLHOLDINGS/szl-model-inference-lab) | fold into szl-serve / szl-command-lab | Space runtime |

## Not public product Spaces

HTTP 401 on Hub API this pass. Do not advertise as LIVE.

- `SZLHOLDINGS/nexus` — runtime is IMMUNE Channel A `/nexus.html`
- `SZLHOLDINGS/anatomy`
- `SZLHOLDINGS/szl-khipu` — public twin is model [SZL-Khipu-1.5B](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B)
- `SZLHOLDINGS/holographic`, `cosmos`, `sda`, `yarqa`, `immune-demo`, `vessels`

## Rule

1. Do not delete `SZLHOLDINGS/immune` or `SZLHOLDINGS/immune-lattice`.
2. Do not mint a public `SZLHOLDINGS/nexus` Space.
3. Flagship GitHub homepages stay on a-11-oy.com / a11oy.net when that is the product URL.
4. Kernel / software twins that lacked a homepage now point at the public Hub model or Space.
5. Frozen 2026-08-29 and 2026-08-31 inventories stay historical.

Lorenz OP (Channel A = Channel B): input `c5fcc5029392a5e4f7cd65a655d5379cd65d8f915b2ee96a1db5d44e35ea2358` · output `4071a2f2faca744907747cb2cc82a9d841e125fa287240505f9f9a8454a399ac`. Energy UNAVAILABLE. Λ = Conjecture 1 OPEN.

This recapture cannot write the Hub from this operator session (no Hub token). Spaces listed above were already uploaded and RUNNING when measured.
