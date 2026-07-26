# Founder breakglass

Breakglass is an auditable exception, never an administrator bypass entry.

1. Open a P0 incident issue with the failed gate, exact risk, rollback, and an
   expiry no later than 72 hours.
2. Obtain the founder's explicit approval in that issue.
3. Apply the smallest temporary exception supported by the platform. Do not
   lower the global approval count, add administrator bypass, force-merge, or
   disable unrelated safeguards.
4. Merge only through a pull request. Record the incident URL, gate, actor,
   start, expiry, and rollback in the merge BAP.
5. Update `KNOWN_LIMITATIONS.md` in the same commit.
6. Revoke the exception immediately after use and attach proof to the incident.
7. The reaper check must fail if an exception or bypass actor is present for
   more than two hours, even when the incident expiry is longer.

If the platform cannot express a narrow exception without weakening a
repository-wide safeguard, the merge remains blocked.
