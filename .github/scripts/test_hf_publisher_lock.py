from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-hf-deploy.yml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
LOCK = ROOT / "requirements" / "hf-publisher.lock"


def main() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    tests_workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
    lock = LOCK.read_text(encoding="utf-8")

    for source in (workflow, tests_workflow):
        assert 'python-version: "3.12.10"' in source
        assert 'VENV="$RUNNER_TEMP/hf-publisher-venv"' in source
        assert 'if [ -e "$VENV" ]; then' in source
        assert 'python3 -m venv "$VENV"' in source
        assert '"$VENV/bin/python" -I -P -c' in source
        assert "--require-hashes" in source
        assert "--only-binary=:all:" in source
        assert "--ignore-installed" in source

    assert "Create fresh publisher virtual environment" in workflow
    assert "github.job_workflow_sha" not in workflow
    assert "repository: ${{ job.workflow_repository }}" in workflow
    assert "ref: ${{ job.workflow_sha }}" in workflow
    assert "EXPECTED_TOOLS_SHA: ${{ job.workflow_sha }}" in workflow
    assert 'ACTUAL_TOOLS_SHA="$(git -C tools rev-parse --verify HEAD)"' in workflow
    assert '[[ ! "$EXPECTED_TOOLS_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[ "$ACTUAL_TOOLS_SHA" != "$EXPECTED_TOOLS_SHA" ]' in workflow
    assert '"$RUNNER_TEMP/hf-publisher-venv/bin/python" -I -P -m pip install' in workflow
    assert "tools/requirements/hf-publisher.lock" in workflow
    assert '"huggingface_hub==1.19.0"' not in workflow
    assert '"requests==2.32.5"' not in workflow
    assert "python3 tools/.github/scripts/hf_" not in workflow
    for script in (
        "hf_deploy_from_dockerfile.py",
        "hf_space_source_binding.py",
    ):
        invocation = (
            '"$RUNNER_TEMP/hf-publisher-venv/bin/python" -I -P '
            f"tools/.github/scripts/{script}"
        )
        assert invocation in workflow

    create = workflow.index("Create fresh publisher virtual environment")
    install = workflow.index("Install hash-locked deployment client closure")
    secret = workflow.index("Require governed publisher")
    assert create < install < secret

    assert "github.job_workflow_sha" not in tests_workflow
    assert "name: Reusable publisher exact-source witness" in tests_workflow
    assert "uses: ./.github/workflows/reusable-hf-deploy.yml" in tests_workflow
    assert "contract-only: true" in tests_workflow
    assert "HF_TOKEN: ${{ github.token }}" in tests_workflow

    assert "HF publisher clean Linux install and runtime proof" in tests_workflow
    assert "python3 -m pip install --dry-run" not in tests_workflow
    assert '"$VENV/bin/python" -I -P -m pip install' in tests_workflow
    for module in (
        "certifi",
        "charset_normalizer",
        "hf_xet",
        "httpcore",
        "httpx",
        "huggingface_hub",
        "requests",
        "urllib3",
        "yaml",
    ):
        assert module in tests_workflow
    assert 'version("huggingface-hub") == "1.19.0"' in tests_workflow
    assert 'version("requests") == "2.32.5"' in tests_workflow
    assert '"$VENV/bin/python" -I -P -m py_compile' in tests_workflow
    assert '"$VENV/bin/python" -I -P .github/scripts/hf_deploy_from_dockerfile.py --help' in tests_workflow
    assert '"$VENV/bin/python" -I -P .github/scripts/hf_space_source_binding.py --help' in tests_workflow
    assert '"$VENV/bin/python" -I -P .github/scripts/test_hf_deploy_from_dockerfile.py' in tests_workflow
    assert '"$VENV/bin/python" -I -P .github/scripts/test_hf_space_source_binding.py' in tests_workflow
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
