from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-hf-deploy.yml"
LOCK = ROOT / "requirements" / "hf-publisher.lock"


def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    lock = LOCK.read_text(encoding="utf-8")

    assert 'python-version: "3.12.10"' in workflow
    assert "--require-hashes" in workflow
    assert "--only-binary=:all:" in workflow
    assert "tools/requirements/hf-publisher.lock" in workflow
    assert '"huggingface_hub==1.19.0"' not in workflow
    assert '"requests==2.32.5"' not in workflow
    assert "--only-binary=:all:" in lock

    entries = re.findall(
        r"(?m)^([a-z0-9][a-z0-9-]*)==([^\s\\]+)\s+\\\n"
        r"\s+--hash=sha256:([0-9a-f]{64})$",
        lock,
    )
    names = [name for name, _, _ in entries]
    assert len(entries) == 26, f"expected 26 locked wheels, found {len(entries)}"
    assert len(names) == len(set(names)), "duplicate package in publisher lock"
    assert {"huggingface-hub", "requests", "hf-xet", "certifi"} <= set(names)


if __name__ == "__main__":
    main()
