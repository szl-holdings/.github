#!/usr/bin/env python3
# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
"""SZL dataset/model admission checks (network-free, stdlib only).

Deterministic checks used before a dataset or model revision is admitted:
duplicate rate, train/eval split overlap (exact and containment), ingest
receipt hash canonicalization, upstream license inheritance, and source terms
that forbid public redistribution. Each check returns status PASS, FAIL or
UNKNOWN with its evidence; admit() is fail-closed and never authorizes
publication, training or any status-label change. A hash match proves byte
identity only, not truth, authorization or eligibility.
"""
from __future__ import annotations
import hashlib, json, re
from collections import Counter
from typing import Iterable

_WS = re.compile(r"\s+")

def norm(s: str) -> str:
    return _WS.sub(" ", str(s).strip().lower())

def row_text(r: dict, roles: tuple[str, ...] | None = ("user",)) -> str:
    """Prompt text used for overlap. roles=None -> whole conversation."""
    if "messages" in r:
        return " || ".join(m.get("content", "") for m in r["messages"]
                           if roles is None or m.get("role") in roles)
    for k in ("text", "problem", "question", "scenario"):
        if k in r:
            return str(r[k])
    return json.dumps(r, sort_keys=True)

def duplicate_rate(rows: list[dict], max_rate: float = 0.05) -> dict:
    keys = [norm(row_text(r, None)) for r in rows]
    n, u = len(keys), len(set(keys))
    rate = 0.0 if n == 0 else (n - u) / n
    top = Counter(keys).most_common(1)[0][1] if keys else 0
    return {"check": "duplicate_rate", "rows": n, "unique": u, "dup_rate": round(rate, 4),
            "max_multiplicity": top, "status": "PASS" if rate <= max_rate else "FAIL"}

def split_overlap(train: list[dict], evals: list[dict], name: str = "eval",
                  mode: str = "exact", min_len: int = 30) -> dict:
    """mode='exact': normalized prompt equality. mode='contains': the eval item's
    normalized text (>= min_len chars) appears inside any normalized train conversation
    (catches benchmark cases embedded in longer SFT prompts)."""
    if mode == "exact":
        t = {norm(row_text(r)) for r in train}
        hits = [i for i, r in enumerate(evals) if norm(row_text(r)) in t]
    else:
        # Compare both the full conversation and the user-turn projection.
        # The latter keeps multi-turn user prompts contiguous, so an eval
        # conversation can be detected even when assistant turns separate the
        # same user turns in the training representation.
        train_blobs = (
            "\\n".join(norm(row_text(r, None)) for r in train),
            "\\n".join(norm(row_text(r)) for r in train),
        )
        hits = []
        for i, r in enumerate(evals):
            candidates = {norm(row_text(r, None)), norm(row_text(r))}
            if any(
                len(candidate) >= min_len
                and any(candidate in blob for blob in train_blobs)
                for candidate in candidates
            ):
                hits.append(i)
    return {"check": f"train_vs_{name}_overlap[{mode}]", "eval_rows": len(evals), "overlapping": len(hits),
            "indices": hits[:20], "status": "PASS" if not hits else "FAIL"}

CANONICALIZATIONS = {
    "raw-bytes": lambda raw, obj: raw,
    "python-json-dumps-default": lambda raw, obj: json.dumps(obj).encode(),
    "json-sorted-compact": lambda raw, obj: json.dumps(obj, sort_keys=True, separators=(",", ":")).encode(),
}

def receipt_hash(raw: bytes, receipt: dict) -> dict:
    """Verify a declared hash without assuming every input is JSON.

    Raw bytes are checked before parsing. JSON-dependent canonicalizations are
    attempted only when the input is valid JSON, so JSONL, parquet, and model
    weight blobs return a bounded result instead of raising.
    """
    want = receipt.get("data_sha256")
    declared = receipt.get("hash_canonicalization")
    matched: list[str] = []
    if hashlib.sha256(raw).hexdigest() == want:
        matched.append("raw-bytes")

    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        obj = None
    if obj is not None:
        for key, canonicalize in CANONICALIZATIONS.items():
            if key == "raw-bytes":
                continue
            if hashlib.sha256(canonicalize(raw, obj)).hexdigest() == want:
                matched.append(key)

    if declared:
        ok = declared in matched
        return {"check": "receipt_hash", "declared": declared, "matched": matched,
                "status": "PASS" if ok else "FAIL"}
    return {"check": "receipt_hash", "declared": None, "matched": matched,
            "status": "UNKNOWN" if matched else "FAIL",
            "note": "byte identity only; canonicalization undeclared" if matched else "no candidate matched"}

# Upstream licenses that may NOT be relabeled as a permissive SPDX id on a derivative
NON_RELABELABLE = {
    "nvidia-open-model-license": "derivatives must ship the NVIDIA Open Model License and a Notice file",
    "llama3.1": "Llama community license terms + attribution",
    "gemma": "Gemma terms of use",
}

def license_inheritance(declared: str | None, base_license: str | None,
                        base_license_name: str | None, has_notice_file: bool) -> dict:
    if base_license is None and base_license_name is None:
        return {"check": "license_inheritance", "status": "UNKNOWN", "note": "base license not resolved"}
    key = (base_license_name or base_license or "").lower()
    if key in NON_RELABELABLE:
        ok = declared not in (None, "apache-2.0", "mit", "cc-by-4.0") and has_notice_file
        return {"check": "license_inheritance", "base": key, "declared": declared,
                "requirement": NON_RELABELABLE[key], "status": "PASS" if ok else "FAIL"}
    return {"check": "license_inheritance", "base": key, "declared": declared,
            "status": "PASS" if declared else "FAIL"}

NO_REDISTRIBUTION_SOURCES = {
    "coinbase": "Coinbase Market Data Terms s.3: no redistribution/Derived Works to third parties without written consent",
}

def source_terms(source_text: str, public: bool) -> dict:
    hits = {k: v for k, v in NO_REDISTRIBUTION_SOURCES.items() if k in source_text.lower()}
    if hits and public:
        return {"check": "source_terms", "status": "FAIL", "hits": hits}
    return {"check": "source_terms", "status": "PASS" if not hits else "PASS_PRIVATE_ONLY", "hits": hits}

def admit(results: Iterable[dict]) -> str:
    """Fail-closed: any FAIL -> BLOCKED, any UNKNOWN -> HOLD, else ADMIT_CANDIDATE.
    Never returns a publication or training authorization."""
    st = [r["status"] for r in results]
    if "FAIL" in st:
        return "BLOCKED"
    if "UNKNOWN" in st:
        return "HOLD"
    return "ADMIT_CANDIDATE"
