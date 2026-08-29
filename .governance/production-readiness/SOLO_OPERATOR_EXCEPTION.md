# SOLO_OPERATOR_EXCEPTION

Status: `ACTIVE_EXPIRING`
Expires: `2026-09-11T23:59:59-04:00`
Independent human approval: `UNAVAILABLE`

Do not fake separation of duties. Until a qualified non-author reviewer exists,
this exception is the honest control:

- exact-head automated review is still required
- commits and tags remain signed
- status checks remain strict and up to date
- promotion remains squash-only
- bypass actors remain forbidden

When the exception expires, T0/T1 merges without an independent non-author
approval are BLOCKED.
