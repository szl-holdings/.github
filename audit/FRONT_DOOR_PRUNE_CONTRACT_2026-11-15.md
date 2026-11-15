# Front-door prune-contract incident and CDN heal (2026-11-15)

Status: REMEDIATED. This record documents the front-door outage window on
protected main, its two distinct root causes, the exact remedies applied, and
the standing contract consequences. It makes no policy change and touches no
machine block.

## Timeline (UTC, 2026-11-15)

- ~02:00 - The static origin https://szlholdings-readme.static.hf.space served
  stale 404 responses while the SZLHOLDINGS/README Space restarted.
- 02:11:18 - Out-of-band heal stamp commit on the Space
  ("trigger static re-serve after stale 404, no content change").
- 02:20:41 - Out-of-band REBUILD_TRIGGER.md committed to the Space with the
  self-declared note "static CDN 404 heal; safe to delete".
- 04:00:05 - PR #1011 merge pushed main to 5845a32ce85a2209597c15b27a903d84bfe4a5a1.
- 04:00:31 - The central autopublish cleanup step retired the remaining legacy
  organization-card collateral on the Space (attempt 1).
- 04:00:34 - "Publish exact protected-main card and verify public readback"
  (run 43674796815, attempt 1) failed closed:
  ContractError "unexpected remote paths would be pruned: REBUILD_TRIGGER.md".
  The publication contract (huggingface/org-card.manifest.json, allowed_deletions
  []) refuses to prune any remote file it did not publish. This is correct
  fail-closed behavior; the error class was a genuine out-of-band remote state,
  not a publisher defect.
- 04:07:30 - REBUILD_TRIGGER.md deleted from the Space (commit 474d74de) using
  the estate Hub credential. Its served purpose (CDN 404 heal) was complete and
  its own content marked it safe to delete. Remote file set then matched the
  manifest exactly.
- 04:08:52 - A rerun of run 43674796815 failed closed at the cleanup step:
  CleanupError "cleanup authority mismatch: GITHUB_RUN_ATTEMPT". The legacy
  cleanup authority (hf_org_card_publish_cleanup.py assert_authority) accepts
  only GITHUB_RUN_ATTEMPT=1 on a protected-main push. Reruns can therefore never
  satisfy it; this is by design and is not a defect.

## Standing contract consequences

1. Rebuild-trigger files are transient operational tools on the Hub. Any file
   left on the org-card Space that the manifest does not publish will fail every
   autopublish attempt closed until removed. Operators must delete heal-trigger
   files once their purpose is served; they must never be added to
   allowed_deletions merely to unblock a run.
2. The front-door lane heals only on the next protected-main push (a fresh
   attempt-1 run). Reruns are structurally unauthorized for the cleanup step.
3. The earlier run 43629945108 failure ("live verification did not converge:
   runtime_files_match=False") was a stale-CDN readback during a Space restart
   window, not a content mismatch; the exact-byte publication itself matched.

## Scope note

This audit record is documentation only. No workflow, contract, manifest, or
Hub state is changed by this commit beyond the file itself.
