#!/usr/bin/env python3
"""Validate the root toolchain and test-to-workflow coverage contract.

This checker is intentionally stdlib-only. It does not infer that a named test
passed; it proves that every discovered Python test is either invoked by a
workflow or loaded by a directly invoked parent suite. It also binds the root
Python version and the repository's declared dependency files to their named
consumers.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import platform
import re
import shlex
from typing import Any


SCHEMA = "szl.repository-verification/v1"
CONTRACT = Path("config/repository-verification.json")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_contract(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = root / CONTRACT
    if not path.is_file():
        return None, [f"missing contract: {CONTRACT.as_posix()}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid contract JSON: {exc}"]
    if not isinstance(value, dict):
        return None, ["contract root must be an object"]
    return value, []


def _discover_tests(root: Path, test_roots: object, errors: list[str]) -> set[str]:
    if not isinstance(test_roots, list) or not test_roots:
        errors.append("test_roots must be a non-empty array")
        return set()
    found: set[str] = set()
    for value in test_roots:
        if not isinstance(value, str) or not value:
            errors.append("every test_roots entry must be a non-empty string")
            continue
        directory = root / value
        if not directory.is_dir():
            errors.append(f"missing test root: {value}")
            continue
        found.update(_relative(path, root) for path in directory.rglob("test_*.py"))
    if not found:
        errors.append("no Python tests discovered")
    return found


def _workflow_text(root: Path, errors: list[str]) -> tuple[dict[str, str], str]:
    directory = root / ".github" / "workflows"
    paths = sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))
    if not paths:
        errors.append("no GitHub Actions workflows discovered")
        return {}, ""
    values: dict[str, str] = {}
    for path in paths:
        try:
            values[_relative(path, root)] = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read workflow {_relative(path, root)}: {exc}")
    return values, "\n".join(values.values())


def _run_commands(workflows: dict[str, str]) -> list[str]:
    """Extract only shell command bodies from YAML ``run`` keys.

    Path filters and comments are deliberately excluded: naming a test as a
    trigger is not evidence that the test is executed.
    """
    commands: list[str] = []
    for text in workflows.values():
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", lines[index])
            if match is None:
                index += 1
                continue
            indent = len(match.group(1).expandtabs(2))
            value = match.group(2).strip()
            if value.startswith(("|", ">")):
                index += 1
                block: list[str] = []
                while index < len(lines):
                    line = lines[index]
                    current = len(line) - len(line.lstrip(" "))
                    if line.strip() and current <= indent:
                        break
                    block.append(line.strip())
                    index += 1
                commands.append("\n".join(block))
            else:
                commands.append(value)
                index += 1
    return commands


def _direct_tests(discovered: set[str], commands: list[str]) -> set[str]:
    command_text = "\n".join(commands)
    direct = {
        path for path in discovered
        if path in command_text or Path(path).name in command_text
    }
    for command in commands:
        if "unittest" not in command or "discover" not in command:
            continue
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            continue
        if "discover" not in tokens or "-s" not in tokens or "-p" not in tokens:
            continue
        try:
            search = tokens[tokens.index("-s") + 1].removeprefix("./").rstrip("/")
            pattern = tokens[tokens.index("-p") + 1]
        except (IndexError, ValueError):
            continue
        prefix = f"{search}/" if search else ""
        direct.update(
            path for path in discovered
            if path.startswith(prefix) and fnmatch.fnmatch(Path(path).name, pattern)
        )
    return direct


def validate(root: Path, *, runtime_version: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    contract, contract_errors = _load_contract(root)
    errors.extend(contract_errors)
    if contract is None:
        return {"schema": SCHEMA, "ok": False, "errors": errors}

    if contract.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")

    version = contract.get("python_version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append("python_version must be an exact X.Y.Z string")
        version = None
    version_path = root / ".python-version"
    observed_version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else None
    if observed_version != version:
        errors.append(f".python-version mismatch: contract={version!r} file={observed_version!r}")
    if runtime_version is not None and runtime_version != version:
        errors.append(
            f"runtime Python mismatch: contract={version!r} runtime={runtime_version!r}"
        )

    workflows, _ = _workflow_text(root, errors)
    tests_workflow = workflows.get(".github/workflows/tests.yml")
    if tests_workflow is None:
        errors.append("missing aggregate workflow: .github/workflows/tests.yml")
    elif version and not re.search(
        rf"python-version:\s*[\"']?{re.escape(version)}[\"']?\s*$",
        tests_workflow,
        flags=re.MULTILINE,
    ):
        errors.append(f"aggregate Tests workflow does not pin Python {version}")

    discovered = _discover_tests(root, contract.get("test_roots"), errors)
    direct = _direct_tests(discovered, _run_commands(workflows))

    indirect_value = contract.get("indirect_tests")
    if not isinstance(indirect_value, list):
        errors.append("indirect_tests must be an array")
        indirect_value = []
    indirect: set[str] = set()
    for index, item in enumerate(indirect_value):
        label = f"indirect_tests[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        path = item.get("path")
        loaded_by = item.get("loaded_by")
        reason = item.get("reason")
        if not all(isinstance(value, str) and value for value in (path, loaded_by, reason)):
            errors.append(f"{label} requires non-empty path, loaded_by and reason")
            continue
        if path in indirect:
            errors.append(f"duplicate indirect test: {path}")
            continue
        indirect.add(path)
        if path not in discovered:
            errors.append(f"indirect test is not discovered: {path}")
        if path in direct:
            errors.append(f"directly invoked test must not be allowlisted as indirect: {path}")
        if loaded_by not in direct:
            errors.append(f"indirect loader is not directly invoked by a workflow: {loaded_by}")
        loader_path = root / loaded_by
        loader_text = loader_path.read_text(encoding="utf-8") if loader_path.is_file() else ""
        module = Path(path).stem
        if not re.search(rf"(?:import|from)\s+{re.escape(module)}\b", loader_text):
            errors.append(f"indirect loader {loaded_by} does not import {module}")

    uncovered = sorted(discovered - direct - indirect)
    for path in uncovered:
        errors.append(f"test has no workflow execution path: {path}")

    dependencies = contract.get("dependency_contracts")
    if not isinstance(dependencies, list) or not dependencies:
        errors.append("dependency_contracts must be a non-empty array")
        dependencies = []
    seen_dependencies: set[str] = set()
    for index, item in enumerate(dependencies):
        label = f"dependency_contracts[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        path = item.get("path")
        scope = item.get("scope")
        if not isinstance(path, str) or not path or not isinstance(scope, str) or not scope:
            errors.append(f"{label} requires non-empty path and scope")
            continue
        if path in seen_dependencies:
            errors.append(f"duplicate dependency contract: {path}")
        seen_dependencies.add(path)
        if not (root / path).is_file():
            errors.append(f"missing dependency contract: {path}")
        consumer = item.get("consumer_workflow")
        tokens = item.get("required_tokens", [])
        if consumer is None and tokens:
            errors.append(f"{label} has required_tokens without consumer_workflow")
        elif consumer is not None:
            if not isinstance(consumer, str) or consumer not in workflows:
                errors.append(f"unknown dependency consumer workflow: {consumer!r}")
                consumer_text = ""
            else:
                consumer_text = workflows[consumer]
            if not isinstance(tokens, list) or not tokens:
                errors.append(f"{label} consumer requires non-empty required_tokens")
            else:
                for token in tokens:
                    if not isinstance(token, str) or not token or token not in consumer_text:
                        errors.append(f"dependency consumer {consumer!r} is missing token {token!r}")

    makefile = root / "Makefile"
    make_text = makefile.read_text(encoding="utf-8") if makefile.is_file() else ""
    if not re.search(r"(?m)^verify:\s*(?:#.*)?$", make_text):
        errors.append("Makefile must expose the root 'verify' target")
    if ".github/scripts/verify_repository_contract.py" not in make_text:
        errors.append("Makefile verify target must invoke the repository contract checker")

    return {
        "schema": SCHEMA,
        "ok": not errors,
        "python_version": version,
        "runtime_python_version": runtime_version,
        "workflow_count": len(workflows),
        "discovered_test_count": len(discovered),
        "direct_test_count": len(direct),
        "indirect_test_count": len(indirect),
        "dependency_contract_count": len(seen_dependencies),
        "errors": errors,
        "boundary": (
            "This validates declared toolchain, dependency and test execution paths. "
            "It does not claim that the tests, workflows, rulesets or deployments passed."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", default=".")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="validate source wiring without asserting the current interpreter version",
    )
    args = parser.parse_args(argv)
    runtime_version = None if args.metadata_only else platform.python_version()
    result = validate(Path(args.repo_path), runtime_version=runtime_version)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
