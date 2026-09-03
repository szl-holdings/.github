#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded executor for the 2026-09-03 SZL frontier payload.

Dry-run is the default. Apply mode may update the reviewed Vessels card, the two
exact metadata fields from .github#617, and dispatch already-reviewed native
workflows. It never changes private-Space visibility, protections, secrets,
provider credentials, Cloudflare state directly, or Nemo signatures/queues.
"""
from frontier_payload.operator import main

if __name__ == "__main__":
    raise SystemExit(main())
