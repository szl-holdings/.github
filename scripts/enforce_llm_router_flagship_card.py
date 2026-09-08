#!/usr/bin/env python3
"""Idempotently preserve the LLM Router flagship on the SZLHOLDINGS card."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SPACE = "SZLHOLDINGS/llm-router-live"
ORG_CARD = "SZLHOLDINGS/README"
BEGIN = "<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->"
END = "<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->"
TERMINAL_FAILURES = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}


class EnforceError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def attr(value: Any, key: str, default: Any = None) -> Any:
    result = getattr(value, key, default)
    if result is not default:
        return result
    raw = getattr(value, "raw", None)
    return raw.get(key, default) if isinstance(raw, Mapping) else default


def insert(existing: str, block: str) -> str:
    block = block.strip() + "\n"
    if BEGIN not in block or END not in block:
        raise EnforceError("card source is missing its markers")
    if BEGIN in existing and END in existing:
        return re.sub(
            re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
            block,
            existing,
            count=1,
            flags=re.DOTALL,
        )
    if existing.startswith("---\n"):
        end = existing.find("\n---\n", 4)
        if end >= 0:
            at = end + 5
            return existing[:at] + "\n\n" + block + "\n" + existing[at:].lstrip("\n")
    return block + "\n" + existing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=900)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    card = args.card.read_text(encoding="utf-8")
    assert BEGIN in card and END in card
    if not args.apply:
        print("router flagship card contract valid")
        return 0

    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise EnforceError("HF_TOKEN is absent")
    try:
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.errors import RepositoryNotFoundError
    except ImportError as exc:
        raise EnforceError("huggingface_hub is unavailable") from exc

    api = HfApi(token=token)
    try:
        before = api.repo_info(repo_id=SPACE, repo_type="space", token=token)
    except RepositoryNotFoundError as exc:
        raise EnforceError("the existing router Space is not visible; no duplicate was created") from exc

    api.update_repo_settings(repo_id=SPACE, repo_type="space", private=False, token=token)
    runtime = api.get_space_runtime(repo_id=SPACE, token=token)
    stage = str(attr(runtime, "stage", "UNKNOWN") or "UNKNOWN").upper()
    if stage != "RUNNING":
        api.restart_space(repo_id=SPACE, token=token)
        deadline = time.monotonic() + args.wait_seconds
        while time.monotonic() < deadline:
            runtime = api.get_space_runtime(repo_id=SPACE, token=token)
            stage = str(attr(runtime, "stage", "UNKNOWN") or "UNKNOWN").upper()
            if stage == "RUNNING":
                break
            if stage in TERMINAL_FAILURES:
                raise EnforceError(f"router Space entered terminal stage {stage}")
            time.sleep(15)
        else:
            raise EnforceError(f"router Space did not reach RUNNING; last stage={stage}")

    org_type = None
    current = ""
    for candidate in ("space", "dataset", "model"):
        try:
            api.repo_info(repo_id=ORG_CARD, repo_type=candidate, token=token)
            org_type = candidate
            try:
                local = hf_hub_download(
                    repo_id=ORG_CARD,
                    repo_type=candidate,
                    filename="README.md",
                    token=token,
                )
                current = Path(local).read_text(encoding="utf-8")
            except Exception:
                current = ""
            break
        except Exception:
            continue
    if org_type is None:
        raise EnforceError("SZLHOLDINGS organization-card repository was not found")

    rendered = insert(current, card)
    api.upload_file(
        repo_id=ORG_CARD,
        repo_type=org_type,
        path_or_fileobj=rendered.encode("utf-8"),
        path_in_repo="README.md",
        commit_message="Preserve SZL LLM Router flagship showcase",
        token=token,
    )
    after = api.repo_info(repo_id=SPACE, repo_type="space", token=token)
    receipt = {
        "schema": "szl.llm-router-flagship-card-enforcement/v1",
        "captured_at": utcnow(),
        "space": SPACE,
        "space_private": bool(attr(after, "private", True)),
        "space_revision": attr(after, "sha"),
        "runtime_stage": stage,
        "organization_card": ORG_CARD,
        "organization_card_type": org_type,
        "marker_present": True,
        "rendered_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "previous_space_revision": attr(before, "sha"),
        "complete": stage == "RUNNING" and bool(attr(after, "private", True)) is False,
        "authorization_proof": False,
    }
    if not receipt["complete"]:
        raise EnforceError("post-write router Space state did not meet the flagship contract")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
