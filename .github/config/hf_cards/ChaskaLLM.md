<!-- SZL-ENTERPRISE-ALIGN -->
[![GitHub](https://img.shields.io/badge/GitHub-szl--holdings%2FChaskaLLM-181717?style=flat-square&logo=github)](https://github.com/szl-holdings/ChaskaLLM) [![SZL](https://img.shields.io/badge/SZL-Soft%20Shield%20CPU-5b8dee?style=flat-square)](https://huggingface.co/SZLHOLDINGS) [![smoke](https://img.shields.io/badge/smoke-SMOKE--4B--LATEST-3af4c8?style=flat-square)](./SMOKE-4B-LATEST.json)


# ChaskaLLM

**SZL Holdings' GPU-less CPU language model for short-turn agent routing.**

ChaskaLLM is the Soft Shield short-talk mouth: a CPU-only deployment of
[`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), packaged as a
**Q4_K_M GGUF** for llama.cpp. It answers greetings, status checks and classify/route turns
locally, so paid and frontier capacity stays for hard work.

> **Honest boundary.** This is a packaging of Qwen3-4B-Instruct-2507, not a from-scratch SZL train
> and not a fine-tune. The weights are byte-identical to Unsloth's Q4_K_M GGUF (see Provenance).
> It is the mouth only. ChaskaClaw and NemoClaw are separate sandbox runtimes and are not in this file.

## 2026-10-28 rebuild: why the base changed

The previous file, `chaskallm-3b.Q4_K_M.gguf`, was a quantization of `Qwen/Qwen2.5-3B-Instruct`.
That model is released under the **Qwen Research License**, which does not allow commercial use,
so it could not be offered under Apache-2.0. It has been **removed** from this repository's main
branch (it remains in the git history).

The replacement base, Qwen3-4B-Instruct-2507, is **Apache-2.0**, a non-thinking instruct model with
the same ChatML prompt format (`<|im_start|>` / `<|im_end|>`).

| | Before | Now |
|---|---|---|
| File | `chaskallm-3b.Q4_K_M.gguf` (removed) | `chaskallm-4b.Q4_K_M.gguf` |
| Base | Qwen2.5-3B-Instruct, 3.09B | Qwen3-4B-Instruct-2507, 4.02B |
| Base license | Qwen Research License (non-commercial) | **Apache-2.0** |
| llama.cpp arch | `qwen2` | `qwen3`; needs a llama.cpp build from April 2025 or later |
| Size | 2.10 GB | 2.50 GB |

**Live service.** chaskaclaw.com is a separate deployment. Until its operator swaps in this file,
it is still serving the previous 3B build, and its `/api/v1/info` still reports the old base.

## Provenance

| | |
|---|---|
| Base model | `Qwen/Qwen3-4B-Instruct-2507` @ `cdbee75f17c01a7cc42f958dc650907174af0554` (Apache-2.0) |
| GGUF source | `unsloth/Qwen3-4B-Instruct-2507-GGUF` @ `a06e946bb6b655725eafa393f4a9745d460374c9`, file `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (Apache-2.0) |
| SHA-256 | `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597` (same as the source file) |
| Quantization | Q4_K_M |
| Changes | File renamed only; no weight changes |

`LICENSE` is the Apache-2.0 text from the base model repository. `NOTICE` carries the attributions.

## License

Code and weights are licensed separately, as the GitHub
[`NOTICE`](https://github.com/szl-holdings/ChaskaLLM/blob/main/NOTICE) explains:

- **Code.** The ChaskaLLM packaging and house API code in
  [github.com/szl-holdings/ChaskaLLM](https://github.com/szl-holdings/ChaskaLLM) is Apache-2.0
  (that repository's `LICENSE`).
- **Weights.** Redistributed weights carry their upstream license. Apache-2.0 on the packaging
  code does not re-license them.
  - `chaskallm-4b.Q4_K_M.gguf`: upstream `Qwen/Qwen3-4B-Instruct-2507` and
    `unsloth/Qwen3-4B-Instruct-2507-GGUF` both declare `license: apache-2.0` on the Hub.
  - `chaskallm-3b.Q4_K_M.gguf` (retired, still in this repository's git history): upstream
    `Qwen/Qwen2.5-3B-Instruct` declares `license: other` / `license_name: qwen-research` on the
    Hub. The Qwen research and upstream notices apply to it.

This section reports upstream Hub metadata. It is not a legal determination.

## Evaluation

CPU smoke test, 2026-10-28. Full receipt: [`SMOKE-4B-LATEST.json`](./SMOKE-4B-LATEST.json).

Run with llama.cpp build 10777, CPU only (no CUDA device visible, `-ngl 0`), 4 threads at
lowest priority on a shared 6-vCPU host, temperature 0.

| Check | Result |
|---|---|
| Exact reply `CHASKA_SMOKE_OK` | PASS |
| "Does ChaskaLLM run on GPU?" answers `NO` first | PASS |
| Product identity `ChaskaLLM` | PASS |
| Route "hey, good morning!" → `GREET` | PASS |
| Route "is the nightly backup done yet?" → `STATUS` | PASS |
| Route "refactor our payment service…" → `ESCALATE` | PASS |
| Raw ChatML prompt (llama.cpp `/completion`), no `<think>` output | PASS |
| **Total** | **7 / 7** |

Generation speed in that test was 5–6 tokens/s on 4 contended threads. That figure is not a
throughput claim for larger hosts; re-measure on the deployment host.

`SMOKE-HQ-LATEST.json` is the receipt for the **retired** 3B build and does not describe this file.
That full receipt ends with `"pass": false`, because its internal 1.1B lane (`chat_fast_1b`)
failed. The PASS badge published for that build covered the 3B lane only
(`publication_badge: PASS_3B_ONLY`, `full_receipt_pass: false` in the GitHub
[`smoke/SCOPE.json`](https://github.com/szl-holdings/ChaskaLLM/blob/main/smoke/SCOPE.json)).
The failed case is preserved in both places.

## Intended use

**In scope:** short greetings and status turns, classify/route decisions before escalating, estate
helpers that must stay measured and fail closed, and edge or air-gapped CPU inference.

**Out of scope:** long-horizon tool use, novel research, code execution, and anything that needs a
frontier model. Escalate those.

## Quickstart (llama.cpp)

```bash
./llama-cli -m chaskallm-4b.Q4_K_M.gguf -ngl 0 -t 12 -c 2048 -n 128 \
  -p '<|im_start|>system
You are ChaskaLLM — SZL Holdings house GPU-less CPU LLM.
Default weights: Qwen/Qwen3-4B-Instruct-2507 Q4_K_M. n_gpu_layers=0.
Never claim you use a GPU. Be brief, precise, factual.
For yes/no questions answer YES or NO first, then one short clause.<|im_end|>
<|im_start|>user
Does ChaskaLLM use a GPU?<|im_end|>
<|im_start|>assistant
' -st --simple-io
```

Or serve it with an OpenAI-compatible endpoint:

```bash
./llama-server -m chaskallm-4b.Q4_K_M.gguf -ngl 0 -c 2048 --host 127.0.0.1 --port 18765
```

## Files

| File | Description |
|---|---|
| `chaskallm-4b.Q4_K_M.gguf` | ChaskaLLM weights (2.50 GB) |
| `SMOKE-4B-LATEST.json` | Smoke receipt for this file |
| `SMOKE-HQ-LATEST.json` | Receipt for the retired 3B build (historical; `"pass": false`, PASS badge scoped to the 3B lane) |
| `LICENSE` | Apache License 2.0 |
| `NOTICE` | Attribution to Qwen (Alibaba Cloud) and Unsloth AI |

## Naming

| Name | What it is |
|---|---|
| **ChaskaLLM** | This repository, a GPU-less CPU LLM |
| **ChaskaClaw** | House OpenShell harness, not an LLM |
| **NemoClaw** | NVIDIA OpenShell code sandbox, not an LLM |

*Ch'aska* is Quechua for the radiant morning and evening star.

---

## SZL estate alignment (docs · 20261102T164419Z)

| Link | Role |
|---|---|
| [szl-holdings/ChaskaLLM](https://github.com/szl-holdings/ChaskaLLM) | Canonical Git (clone may lag house live tree) |
| [SZLHOLDINGS org](https://huggingface.co/SZLHOLDINGS) | Hub artifact registry |
| Collection plan | `chaskallm-soft-shield` (steward enterprise pack) |

**Smoke:** see `SMOKE-4B-LATEST.json` in this repo.  
**Promote law:** candidate → authenticated weights require Stephen `GO WEIGHT <id>` — never invent GO.  
**Face:** Stephen Lutar · CTO · SZL Holdings Inc.

## Governance

- Hub repository: `SZLHOLDINGS/ChaskaLLM`
- Source of truth: [github.com/szl-holdings/ChaskaLLM](https://github.com/szl-holdings/ChaskaLLM)
- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE
- Receipts remain UNSIGNED_HONEST until the DSSE lane signs
