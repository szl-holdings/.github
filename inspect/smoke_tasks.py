# szl-holdings/.github/inspect/smoke_tasks.py
# SZL Holdings — Flagship smoke tests as Inspect AI Task format
# Inspired by UK AISI Inspect framework for reproducible LLM/system evaluation.
# Doctrine v11 LOCKED 749/14/163. SLSA L1 honest.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>

from dataclasses import dataclass
from typing import Literal

BASE = "https://szlholdings-{}.hf.space"

@dataclass
class SmokeTask:
    id: str
    flagship: str
    endpoint: str
    method: Literal["GET", "POST"]
    expected_status: int
    expected_fields: list[str]
    doctrine_check: bool = True

SZL_SMOKE_TASKS = [
    SmokeTask("T-A11OY-01", "a11oy", "/api/a11oy/healthz", "GET", 200, ["status"]),
    SmokeTask("T-A11OY-02", "a11oy", "/api/a11oy/v1/lambda", "GET", 200, ["lambda", "declarations"]),
    SmokeTask("T-SENTRA-01", "sentra", "/api/sentra/v1/lambda", "GET", 200, ["lambda", "doctrine"]),
    SmokeTask("T-ROSIE-01", "rosie", "/api/rosie/v1/lambda", "GET", 200, ["lambda", "declarations"]),
    SmokeTask("T-KILLINCHU-01", "killinchu", "/api/killinchu/v1/honest", "GET", 200,
              ["doctrine", "declarations", "kernel_commit"]),
]

def run_smoke(task: SmokeTask) -> dict:
    import urllib.request, json
    url = BASE.format(task.flagship) + task.endpoint
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            status = r.status
            body = json.loads(r.read())
            missing = [f for f in task.expected_fields if f not in body]
            return {"task": task.id, "status": status, "pass": status == task.expected_status and not missing,
                    "missing_fields": missing, "url": url}
    except Exception as e:
        return {"task": task.id, "pass": False, "error": str(e), "url": url}

if __name__ == "__main__":
    import json
    results = [run_smoke(t) for t in SZL_SMOKE_TASKS]
    print(json.dumps(results, indent=2))
