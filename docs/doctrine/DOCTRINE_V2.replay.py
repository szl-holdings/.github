#!/usr/bin/env python3
"""
DOCTRINE_V2.replay.py — SHA-256 hash stability check for DOCTRINE_V2.md.

Reads DOCTRINE_V2.md 5× with seeds [42, 137, 256, 512, 1024].
Seeds are recorded for traceability but the content is deterministic
(static file) — the SHA-256 of the file bytes must be identical across
all 5 reads.
Prints per-seed hash + final PASS/FAIL.
Exits 0 on PASS, 1 on FAIL.

Author: Stephen P. Lutar Jr. <stephen@szlholdings.com>
Doctrine: v2 binding
"""

import hashlib
import sys
from pathlib import Path

SEEDS = [42, 137, 256, 512, 1024]

# Resolve DOCTRINE_V2.md relative to this script's location
SCRIPT_DIR = Path(__file__).parent.resolve()
DOC_PATH = SCRIPT_DIR / "DOCTRINE_V2.md"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of the file bytes (pure content hash)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not DOC_PATH.exists():
        print(f"[ERROR] DOCTRINE_V2.md not found at: {DOC_PATH}", file=sys.stderr)
        return 1

    file_size = DOC_PATH.stat().st_size
    print(f"DOCTRINE_V2.replay — file: {DOC_PATH}")
    print(f"  size : {file_size} bytes")
    print(f"  seeds: {SEEDS}")
    print()

    hashes: list[str] = []
    for seed in SEEDS:
        # Seeds are recorded for traceability; content is static/deterministic.
        # Each read independently verifies the file hash is stable.
        digest = sha256_file(DOC_PATH)
        hashes.append(digest)
        print(f"  seed={seed:<6}  sha256={digest}")

    print()

    unique_hashes = set(hashes)
    if len(unique_hashes) == 1:
        print(f"  unique hash count : 1 of {len(SEEDS)} ✅")
        print()
        print(f"[DOCTRINE PASS] DOCTRINE_V2.md is byte-identical across all {len(SEEDS)} reads.")
        print(f"  canonical sha256: {hashes[0]}")
        return 0
    else:
        print(f"  unique hash count : {len(unique_hashes)} of {len(SEEDS)} ❌")
        print()
        print("[DOCTRINE FAIL] Hash mismatch — file is not byte-identical across reads.")
        for i, (seed, digest) in enumerate(zip(SEEDS, hashes)):
            print(f"  run {i + 1} seed={seed}: {digest}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
