#!/usr/bin/env python3
"""Compatibility entrypoint for the current GitHub CheckRun GraphQL schema.

GitHub no longer exposes ``CheckRun.app`` on the schema used by this workflow.
The underlying verifier does not depend on that field for any decision; it was
report-only metadata.  Remove only that selection and run the original exact-SHA,
check-rollup, review-thread, review-decision, mergeability, and admin-authority
logic unchanged.
"""
from __future__ import annotations

import owner_authorized_merge_wave as wave

_OBSOLETE_SELECTION = "                    app { slug }\n"
if _OBSOLETE_SELECTION not in wave.PR_QUERY:
    raise SystemExit("expected obsolete CheckRun.app selection was not found")
wave.PR_QUERY = wave.PR_QUERY.replace(_OBSOLETE_SELECTION, "")

raise SystemExit(wave.main())
