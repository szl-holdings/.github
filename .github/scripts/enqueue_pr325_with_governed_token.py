#!/usr/bin/env python3
"""Enqueue only the exact signed PR #325 head through the governed controller."""
from __future__ import annotations

import request_exact_clean_merge_queue as preflight
import enqueue_with_governed_user_tokens as controller

preflight.TARGETS = (
    preflight.Target(
        number=325,
        head_sha="93a5138742497345cca21b8bd1a385d3b499c579",
        base_sha="527fd000c5189f7b1ca4e56b7993d1daa952308a",
    ),
)


if __name__ == "__main__":
    raise SystemExit(controller.main())
