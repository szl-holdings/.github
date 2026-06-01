#!/usr/bin/env python3
"""
Push resilience+observability patches to existing HuggingFace Spaces via HfApi.
ADDITIVE ONLY: drops patches under resilience/ subfolder, never overwrites
serve.py / Dockerfile / szl_wire.py. Token auth, NEVER GitHub Actions secrets.HF_TOKEN.
Doctrine v12 (additive over v11 LOCKED 749/14/163). Signed: Yachay, under CTO authority.
"""
import json
from pathlib import Path
from huggingface_hub import HfApi, CommitOperationAdd

TOKEN = open("/home/user/workspace/szl/audit_2026-05-30_cursor_offline/.secret/hf_token").read().strip()
PATCH = Path("/home/user/workspace/szl/audit_2026-05-30_cursor_offline/round2/full_reaudit_2026-05-31/resilience_observability/patches")

api = HfApi(token=TOKEN)
results = {}

# Confirmed-existing Python (Docker) Spaces from hf inventory. killinchu NOT created -> skipped.
PY_SPACES = ["a11oy", "amaru", "sentra", "vessels", "rosie"]

COMMON_MSG = (
    "feat(resilience): add circuit-breaker + observability patches (Doctrine v12, ADDITIVE). "
    "resilience/szl_breaker.py: pybreaker+tenacity CLOSED/OPEN/HALF-OPEN wrapper. "
    "resilience/szl_exporter.py: Prometheus exporter scraping breaker/healthz state. "
    "resilience/status_feed.py: fail-closed internal->public status filter (KEY-name allowlist). "
    "HONEST: in-memory buses; Sigstore sig PLACEHOLDER; SLSA L1; no cross-Space tracing. "
    "Does NOT modify serve.py/Dockerfile. ZERO BANDAID. Yachay, under CTO authority."
)

def push(space, ops, msg, key=None):
    key = key or space
    print(f"\n=== Pushing {space} ({key}) ===")
    try:
        res = api.create_commit(
            repo_id=f"SZLHOLDINGS/{space}",
            repo_type="space",
            operations=ops,
            commit_message=msg,
        )
        sha = res.oid if hasattr(res, "oid") else str(res)
        print(f"{space} SUCCESS SHA: {sha}")
        results[key] = {"space": space, "sha": sha, "status": "OK"}
    except Exception as e:
        import traceback; traceback.print_exc()
        results[key] = {"space": space, "sha": None, "status": f"FAIL: {e}"}

# Python spaces: breaker + exporter + status_feed
for sp in PY_SPACES:
    ops = [
        CommitOperationAdd("resilience/szl_breaker.py",  str(PATCH / "szl_breaker.py")),
        CommitOperationAdd("resilience/szl_exporter.py", str(PATCH / "szl_exporter.py")),
        CommitOperationAdd("resilience/status_feed.py",  str(PATCH / "status_feed.py")),
    ]
    push(sp, ops, COMMON_MSG)

# a11oy also gets the TS breaker for its Node:8081 side
a11oy_ts_msg = (
    "feat(resilience): add TS circuit breaker for a11oy Node orchestrator (Doctrine v12, ADDITIVE). "
    "resilience/szlBreaker.ts: cockatiel CLOSED/OPEN/HALF-OPEN around LLM router calls. "
    "Additive; does not modify existing Node sources. Yachay, under CTO authority."
)
push_a11oy_ts = [CommitOperationAdd("resilience/szlBreaker.ts", str(PATCH / "szlBreaker.ts"))]
push("a11oy", push_a11oy_ts, a11oy_ts_msg, key="a11oy_ts")

out = Path("/home/user/workspace/szl/audit_2026-05-30_cursor_offline/round2/full_reaudit_2026-05-31/resilience_observability/HF_PUSH_SHAS.json")
out.write_text(json.dumps(results, indent=2))
print("\n=== SUMMARY ===")
print(json.dumps(results, indent=2))
