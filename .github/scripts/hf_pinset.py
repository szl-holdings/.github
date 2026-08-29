#!/usr/bin/env python3
"""Set the Hub pin set. GitHub origin, Hub mirror. Nothing live is frozen."""

from __future__ import annotations

import os
import sys

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.repocard import RepoCard

PIN = [
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/killinchu",
    "SZLHOLDINGS/immune",
    "SZLHOLDINGS/szl-atelier",
    "SZLHOLDINGS/holographic",
]
UNPIN = [
    "SZLHOLDINGS/cosmos",
    "SZLHOLDINGS/SZL-Cosmos",
    "SZLHOLDINGS/SZL-KHIPU",
    "SZLHOLDINGS/szl-khipu",
    "SZLHOLDINGS/Khipu-Loom",
    "SZLHOLDINGS/szl-estate-live",
]
FACTORY = "SZLHOLDINGS/a11oy-factory"


def set_space_pinned(api: HfApi, repo_id: str, pinned: bool) -> str:
    try:
        card = RepoCard.load(repo_id, repo_type="space", token=api.token)
    except Exception as exc:  # noqa: BLE001 — missing card is UNAVAILABLE, not a crash
        return f"UNAVAILABLE load {repo_id}: {exc}"
    data = card.data
    current = bool(getattr(data, "pinned", False))
    if current == pinned:
        return f"MEASURED already {'pinned' if pinned else 'unpinned'} {repo_id}"
    try:
        data.pinned = pinned
    except Exception:
        data["pinned"] = pinned
    try:
        card.push_to_hub(
            repo_id,
            repo_type="space",
            token=api.token,
            commit_message=("Pin flagship Hub card" if pinned else "Unpin Hub card — not a flagship"),
        )
    except HfHubHTTPError as exc:
        return f"BLOCKED push {repo_id}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"BLOCKED push {repo_id}: {exc}"
    return f"MEASURED set pinned={pinned} {repo_id}"


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_ORG_TOKEN1")
    if not token:
        print("HF_TOKEN absent. Hub mutation BLOCKED.", file=sys.stderr)
        return 1
    api = HfApi(token=token)
    results = []
    for repo in PIN:
        results.append(set_space_pinned(api, repo, True))
    for repo in UNPIN:
        results.append(set_space_pinned(api, repo, False))
    results.append(set_space_pinned(api, FACTORY, False))
    for line in results:
        print(line)
    blocked = [r for r in results if r.startswith("BLOCKED")]
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
