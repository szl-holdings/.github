#!/usr/bin/env python3
"""Emit a deterministic, fail-closed delta of control-plane side effects.

The analyzer is deliberately static and network-free. It recognizes a bounded
grammar of GitHub workflow actions, shell commands, inline Python, and
repository-local Python/scripts. Anything executable outside that grammar is
UNKNOWN_EFFECT and therefore denied. This establishes a reviewed static effect
boundary; it does not claim arbitrary-program formal verification.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


POLICY_SCHEMA = "szl.control-plane-effect-policy/v1"
RECEIPT_SCHEMA = "szl.control-plane-effect-delta/v1"
DEFAULT_POLICY_PATH = ".github/data/control_plane_effect_policy.json"
EXACT_SHA = re.compile(r"[0-9a-f]{40}")
EXACT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
SECRET_REFERENCE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MUTATING_HTTP_VERBS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ACCESS_MODES = frozenset({"read", "local-write", "external-write"})
TRUSTED_TOOL_PATHS = frozenset(
    {
        ".github/scripts/control_plane_effect_gate.py",
        ".github/scripts/test_control_plane_effect_gate.py",
    }
)
TRUST_ROOT_PATHS = frozenset(
    {
        DEFAULT_POLICY_PATH,
        ".github/scripts/control_plane_effect_gate.py",
        ".github/scripts/test_control_plane_effect_gate.py",
        ".github/workflows/control-plane-effect-gate.yml",
        "docs/CONTROL_PLANE_EFFECTS.md",
    }
)
SAFE_REPO_PATH = re.compile(r"[A-Za-z0-9._/-]+")

# Exact action classifications are part of the analyzer's trusted computing
# base. An unknown external action is denied rather than optimistically called
# read-only.
KNOWN_ACTION_EFFECTS: Mapping[str, tuple[str, str, str]] = {
    "step-security/harden-runner@e14015d583714f6e62063499dc959a02595150a1": (
        "runner.guard.configure",
        "runner:guard:egress",
        "local-write",
    ),
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1": (
        "github.contents.checkout",
        "github:repository:szl-holdings/.github:contents",
        "read",
    ),
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97": (
        "runner.toolchain.install",
        "runner:toolchain:python",
        "local-write",
    ),
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": (
        "github.artifact.upload",
        "github:actions:artifact:control-plane-effect",
        "external-write",
    ),
}

PYTHON_MUTATORS: Mapping[str, str] = {
    "add_space_secret": "sdk.huggingface.add_space_secret",
    "add_space_variable": "sdk.huggingface.add_space_variable",
    "create_commit": "sdk.repository.create_commit",
    "create_repo": "sdk.repository.create",
    "delete_repo": "sdk.repository.delete",
    "merge": "sdk.github.merge",
    "move_repo": "sdk.repository.move",
    "pause_space": "sdk.huggingface.pause_space",
    "push_to_hub": "sdk.huggingface.push_to_hub",
    "request_space_hardware": "sdk.huggingface.request_space_hardware",
    "restart_space": "sdk.huggingface.restart_space",
    "update_repo_settings": "sdk.huggingface.update_repo_settings",
    "upload_file": "sdk.repository.upload_file",
    "upload_folder": "sdk.repository.upload_folder",
}

LOCAL_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:\./)?(?:\.github|scripts|tools|actions)/"
    r"[A-Za-z0-9_.\-/]+\.(?:py|sh|bash|ps1|js|mjs|cjs|ts|json|yml|yaml))"
    r"(?![A-Za-z0-9_.-])"
)


class GateError(RuntimeError):
    """Policy, repository, or analysis state cannot be trusted."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, order=True)
class RawEffect:
    sink: str
    access: str
    path: str
    line: int
    resource: str = ""

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        if not value["resource"]:
            value.pop("resource")
        return value


@dataclass(frozen=True, order=True)
class UnknownEffect:
    code: str
    path: str
    line: int

    def public(self) -> dict[str, Any]:
        return asdict(self)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_repo_path(value: str) -> str:
    if not isinstance(value, str) or not SAFE_REPO_PATH.fullmatch(value):
        raise GateError("UNSAFE_PATH", "repository path contains unsupported characters")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(part in {"", "."} for part in value.split("/"))
        or path.as_posix() != value
    ):
        raise GateError("UNSAFE_PATH", "repository paths must be relative and traversal-free")
    return value


def strict_json(raw: bytes) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise GateError("POLICY_DUPLICATE_KEY", "JSON object repeats a key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> Any:
        raise GateError("POLICY_NONFINITE_NUMBER", "non-finite JSON numbers are denied")

    try:
        return json.loads(
            raw,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("POLICY_UNREADABLE", "effect policy is invalid JSON") from exc


def strict_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise GateError("POLICY_SCHEMA_INVALID", f"{label} has missing or unknown keys")


def parse_iso_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise GateError("POLICY_SCHEMA_INVALID", f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GateError("POLICY_SCHEMA_INVALID", f"{label} must be an ISO date") from exc


def validate_digest(value: Any, label: str) -> str:
    text = str(value or "").lower()
    if not EXACT_DIGEST.fullmatch(text):
        raise GateError("POLICY_SCHEMA_INVALID", f"{label} must be sha256 plus 64 hex")
    return text


def validate_resource_key(value: Any) -> str:
    text = str(value or "")
    if not SAFE_IDENTIFIER.fullmatch(text) or any(
        token in text for token in ("*", "?", "[", "]")
    ):
        raise GateError(
            "WILDCARD_RESOURCE_DENIED",
            "resource keys must be exact, literal, and wildcard-free",
        )
    return text


def load_policy_bytes(raw: bytes, *, as_of: date) -> dict[str, Any]:
    policy = strict_json(raw)
    if not isinstance(policy, dict):
        raise GateError("POLICY_SCHEMA_INVALID", "effect policy root must be an object")
    strict_keys(
        policy,
        {
            "schema",
            "valid_from",
            "valid_until",
            "default_decision",
            "unknown_effect",
            "wildcard_resources",
            "workflow_declarations",
        },
        "policy",
    )
    if policy["schema"] != POLICY_SCHEMA:
        raise GateError("POLICY_SCHEMA_INVALID", "unexpected effect-policy schema")
    if (
        policy["default_decision"] != "deny"
        or policy["unknown_effect"] != "deny"
        or policy["wildcard_resources"] != "deny"
    ):
        raise GateError("POLICY_WEAKENED", "policy defaults must remain deny")
    valid_from = parse_iso_date(policy["valid_from"], "policy.valid_from")
    valid_until = parse_iso_date(policy["valid_until"], "policy.valid_until")
    if valid_until < valid_from or not (valid_from <= as_of <= valid_until):
        raise GateError("POLICY_EXPIRED", "effect policy is not valid on the analysis date")

    declarations = policy["workflow_declarations"]
    if not isinstance(declarations, dict) or not declarations:
        raise GateError(
            "POLICY_SCHEMA_INVALID", "workflow_declarations must be a non-empty object"
        )
    normalized: dict[str, Any] = {}
    for workflow_path, declaration in declarations.items():
        workflow = safe_repo_path(workflow_path)
        if not workflow.startswith(".github/workflows/") or not workflow.endswith(
            (".yml", ".yaml")
        ):
            raise GateError(
                "POLICY_SCHEMA_INVALID", "declaration keys must name workflow YAML files"
            )
        if not isinstance(declaration, dict):
            raise GateError("POLICY_SCHEMA_INVALID", "workflow declaration must be an object")
        strict_keys(
            declaration,
            {
                "intent_id",
                "valid_until",
                "source_sha256",
                "credentials",
                "resources",
                "effects",
                "max_external_writes",
                "required_controls",
                "trusted_transitives",
            },
            f"declaration {workflow}",
        )
        intent_id = str(declaration["intent_id"] or "")
        if not SAFE_IDENTIFIER.fullmatch(intent_id):
            raise GateError("POLICY_SCHEMA_INVALID", "intent_id must be a safe identifier")
        declaration_until = parse_iso_date(
            declaration["valid_until"], f"{workflow}.valid_until"
        )
        if declaration_until < as_of or declaration_until > valid_until:
            raise GateError(
                "INTENT_EXPIRED", "workflow intent is expired or outlives its policy"
            )
        source_digest = validate_digest(
            declaration["source_sha256"], f"{workflow}.source_sha256"
        )

        credentials = declaration["credentials"]
        if (
            not isinstance(credentials, list)
            or any(
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(item))
                for item in credentials
            )
            or len(credentials) != len(set(credentials))
        ):
            raise GateError(
                "POLICY_SCHEMA_INVALID",
                "credentials must be unique literal secret names",
            )
        credentials = sorted(str(item) for item in credentials)

        resources = declaration["resources"]
        if not isinstance(resources, list) or not resources:
            raise GateError("POLICY_SCHEMA_INVALID", "resources must be a non-empty list")
        resource_map: dict[str, str] = {}
        normalized_resources: list[dict[str, str]] = []
        for item in resources:
            if not isinstance(item, dict):
                raise GateError("POLICY_SCHEMA_INVALID", "resource entries must be objects")
            strict_keys(item, {"key", "access"}, "resource")
            key = validate_resource_key(item["key"])
            access = str(item["access"])
            if access not in ACCESS_MODES or key in resource_map:
                raise GateError(
                    "POLICY_SCHEMA_INVALID",
                    "resource keys must be unique and use a supported access mode",
                )
            resource_map[key] = access
            normalized_resources.append({"key": key, "access": access})

        effects = declaration["effects"]
        if not isinstance(effects, list):
            raise GateError("POLICY_SCHEMA_INVALID", "effects must be a list")
        normalized_effects: list[dict[str, Any]] = []
        effect_keys: set[tuple[str, str]] = set()
        for item in effects:
            if not isinstance(item, dict):
                raise GateError("POLICY_SCHEMA_INVALID", "effect entries must be objects")
            strict_keys(item, {"sink", "resource", "access", "max_calls"}, "effect")
            sink = str(item["sink"] or "")
            resource = validate_resource_key(item["resource"])
            access = str(item["access"])
            max_calls = item["max_calls"]
            if (
                not SAFE_IDENTIFIER.fullmatch(sink)
                or access not in ACCESS_MODES
                or not isinstance(max_calls, int)
                or isinstance(max_calls, bool)
                or max_calls < 1
                or resource_map.get(resource) != access
                or (sink, resource) in effect_keys
            ):
                raise GateError(
                    "POLICY_SCHEMA_INVALID",
                    "effects must bind unique sinks to declared resources and budgets",
                )
            effect_keys.add((sink, resource))
            normalized_effects.append(
                {
                    "sink": sink,
                    "resource": resource,
                    "access": access,
                    "max_calls": max_calls,
                }
            )
        max_external = declaration["max_external_writes"]
        if (
            not isinstance(max_external, int)
            or isinstance(max_external, bool)
            or max_external < 0
        ):
            raise GateError(
                "POLICY_SCHEMA_INVALID",
                "max_external_writes must be a non-negative integer",
            )

        controls = declaration["required_controls"]
        if not isinstance(controls, dict):
            raise GateError("POLICY_SCHEMA_INVALID", "required_controls must be an object")
        strict_keys(
            controls,
            {
                "triggers",
                "contents_read",
                "no_explicit_secrets",
                "concurrency",
                "protected_ref",
                "exact_sha",
                "expected_before",
                "readback",
            },
            "required_controls",
        )
        triggers = controls["triggers"]
        if (
            not isinstance(triggers, list)
            or not triggers
            or any(not SAFE_IDENTIFIER.fullmatch(str(item)) for item in triggers)
            or len(triggers) != len(set(triggers))
        ):
            raise GateError("POLICY_SCHEMA_INVALID", "required triggers must be unique")
        for key in (
            "contents_read",
            "no_explicit_secrets",
            "concurrency",
            "protected_ref",
            "exact_sha",
            "expected_before",
            "readback",
        ):
            if not isinstance(controls[key], bool):
                raise GateError("POLICY_SCHEMA_INVALID", f"control {key} must be boolean")

        trusted = declaration["trusted_transitives"]
        if not isinstance(trusted, dict):
            raise GateError(
                "POLICY_SCHEMA_INVALID", "trusted_transitives must be an object"
            )
        normalized_trusted: dict[str, str] = {}
        for item_path, digest in trusted.items():
            trusted_path = safe_repo_path(item_path)
            if trusted_path not in TRUSTED_TOOL_PATHS:
                raise GateError(
                    "TRUST_EXPANSION_DENIED",
                    "only the fixed CP-eBOM tool and its self-test may be trusted",
                )
            normalized_trusted[trusted_path] = validate_digest(
                digest, f"{workflow}.trusted_transitives.{trusted_path}"
            )

        normalized[workflow] = {
            "intent_id": intent_id,
            "valid_until": declaration_until.isoformat(),
            "source_sha256": source_digest,
            "credentials": credentials,
            "resources": sorted(normalized_resources, key=lambda item: item["key"]),
            "effects": sorted(
                normalized_effects, key=lambda item: (item["sink"], item["resource"])
            ),
            "max_external_writes": max_external,
            "required_controls": {
                **controls,
                "triggers": sorted(str(item) for item in triggers),
            },
            "trusted_transitives": dict(sorted(normalized_trusted.items())),
        }
    policy["workflow_declarations"] = dict(sorted(normalized.items()))
    policy["_sha256"] = sha256_bytes(raw)
    return policy


def load_policy(path: Path, *, as_of: date) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GateError("POLICY_UNREADABLE", "effect policy is missing") from exc
    return load_policy_bytes(raw, as_of=as_of)


def uncommented_yaml(source: str) -> str:
    return "\n".join(
        "" if line.lstrip().startswith("#") else line for line in source.splitlines()
    )


def workflow_triggers(source: str) -> list[str]:
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r'^(?:"on"|on):\s*(.*)$', line)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline:
            if inline.startswith("[") and inline.endswith("]"):
                return sorted(
                    item.strip(" '\"")
                    for item in inline[1:-1].split(",")
                    if item.strip(" '\"")
                )
            if inline == "{}":
                return []
            return [inline.strip(" '\"")]
        found: list[str] = []
        for child in lines[index + 1 :]:
            if child and not child.startswith((" ", "\t")):
                break
            key = re.match(r"^\s{2}([A-Za-z_][A-Za-z0-9_-]*):", child)
            if key:
                found.append(key.group(1))
        return sorted(set(found))
    return []


def workflow_permissions(source: str) -> list[str]:
    lines = source.splitlines()
    found: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)permissions:\s*(.*)$", line)
        if not match:
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline:
            found.append(inline)
            continue
        for child in lines[index + 1 :]:
            if not child.strip():
                continue
            child_indent = len(child) - len(child.lstrip())
            if child_indent <= indent:
                break
            item = re.match(
                r"^\s*([A-Za-z_][A-Za-z0-9_-]*):\s*(read|write|none)\s*(?:#.*)?$",
                child,
            )
            if item:
                found.append(f"{item.group(1)}:{item.group(2)}")
    return sorted(set(found))


def run_blocks(source: str) -> list[tuple[int, str]]:
    lines = source.splitlines()
    blocks: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)(?:-\s*)?run:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        value = match.group(2).strip()
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            body: list[str] = []
            start = index + 2
            index += 1
            while index < len(lines):
                child = lines[index]
                if child.strip():
                    child_indent = len(child) - len(child.lstrip())
                    if child_indent <= indent:
                        break
                    body.append(child[indent + 2 :])
                else:
                    body.append("")
                index += 1
            blocks.append((start, "\n".join(body)))
            continue
        blocks.append((index + 1, value))
        index += 1
    return blocks


def workflow_dependencies(source: str) -> list[str]:
    clean = uncommented_yaml(source)
    dependencies: set[str] = set()
    for match in LOCAL_PATH.finditer(clean):
        spelling = match.group(1)
        # A leading ./ is GitHub's explicit repository-local uses syntax.
        # The policy and receipt still use one canonical Git-tree path.
        dependency = spelling[2:] if spelling.startswith("./") else spelling
        dependencies.add(safe_repo_path(dependency))
    return sorted(dependencies)


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def literal_command(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return None
            values.append(item.value)
        return " ".join(values)
    return None


def shell_effects(
    source: str, *, path: str, line_offset: int = 0
) -> tuple[list[RawEffect], list[UnknownEffect]]:
    effects: list[RawEffect] = []
    unknowns: list[UnknownEffect] = []
    for relative_line, raw_line in enumerate(source.splitlines(), start=1):
        line_no = line_offset + relative_line
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # The recognized sinks below enrich review evidence. A shell command
        # cannot earn ALLOW merely because no known sink pattern matched it:
        # aliases, functions, sourced scripts, CLI subcommands, and shell
        # composition can all hide outbound mutations.
        if stripped not in {"true", ":", "set -euo pipefail"}:
            unknowns.append(
                UnknownEffect("SHELL_COMMAND_UNCLASSIFIED", path, line_no)
            )
        if re.search(
            r"\b(eval|Invoke-Expression|source|dotnet-script)\b|^\s*\.\s+\S",
            stripped,
            re.I,
        ):
            unknowns.append(UnknownEffect("DYNAMIC_EXECUTION", path, line_no))
        if re.search(
            r"(\$\(|\$\{|\$[A-Za-z_]|\x60|base64|\\$|"
            r"\|\s*(?:bash|sh|python|gh|curl))",
            stripped,
        ):
            unknowns.append(UnknownEffect("SHELL_COMPOSITION_UNKNOWN", path, line_no))
        if re.search(r"\b(python3?|node)\s+-[ce]\b", stripped):
            unknowns.append(UnknownEffect("INLINE_DYNAMIC_CODE", path, line_no))

        if re.search(r"\bcurl(?:\.exe)?\b", stripped, re.I):
            unknowns.append(UnknownEffect("HTTP_TARGET_UNRESOLVED", path, line_no))
            explicit = re.search(
                r"(?:^|\s)(?:-X|--request)(?:=|\s+)([^\s\\]+)", stripped
            )
            if explicit:
                method = explicit.group(1).strip("'\"").upper()
                if "$" in method or not re.fullmatch(r"[A-Z]+", method):
                    unknowns.append(UnknownEffect("CURL_DYNAMIC_METHOD", path, line_no))
                elif method in MUTATING_HTTP_VERBS:
                    effects.append(
                        RawEffect(
                            f"http.{method.lower()}", "external-write", path, line_no
                        )
                    )
            elif re.search(
                r"(?:^|\s)(?:-d|--data|--data-raw|--form|-F|-T|--upload-file)(?:=|\s)",
                stripped,
            ):
                effects.append(RawEffect("http.post", "external-write", path, line_no))

        if re.search(r"\bgh\s+api\b", stripped):
            unknowns.append(UnknownEffect("GITHUB_TARGET_UNRESOLVED", path, line_no))
            explicit = re.search(
                r"(?:^|\s)(?:-X|--method)(?:=|\s+)([^\s\\]+)", stripped
            )
            if explicit:
                method = explicit.group(1).strip("'\"").upper()
                if "$" in method or not re.fullmatch(r"[A-Z]+", method):
                    unknowns.append(
                        UnknownEffect("GH_API_DYNAMIC_METHOD", path, line_no)
                    )
                elif method in MUTATING_HTTP_VERBS:
                    effects.append(
                        RawEffect(
                            f"github.api.{method.lower()}",
                            "external-write",
                            path,
                            line_no,
                        )
                    )
            elif re.search(
                r"(?:^|\s)(?:-f|-F|--field|--raw-field)(?:=|\s)", stripped
            ):
                effects.append(
                    RawEffect("github.api.post", "external-write", path, line_no)
                )

        if re.search(r"\bgit\b[^\n]*\bpush\b", stripped):
            unknowns.append(UnknownEffect("GIT_REMOTE_UNRESOLVED", path, line_no))
            effects.append(
                RawEffect("git.remote.push", "external-write", path, line_no)
            )
        if re.search(
            r"\b(?:gh\s+(?:issue|secret|variable|workflow|repo|pr|release)|"
            r"docker\s+push|npm\s+publish|"
            r"(?:hf|huggingface-cli)\s+upload|"
            r"(?:wrangler|vercel)\s+deploy|"
            r"Invoke-(?:RestMethod|WebRequest))\b",
            stripped,
            re.I,
        ):
            unknowns.append(UnknownEffect("EXTERNAL_TARGET_UNRESOLVED", path, line_no))
        command_sinks = (
            (r"(^|\s)docker\s+push\b", "registry.container.push"),
            (r"(^|\s)npm\s+publish\b", "registry.npm.publish"),
            (r"(^|\s)(?:hf|huggingface-cli)\s+upload\b", "huggingface.upload"),
            (r"(^|\s)gh\s+pr\s+merge\b", "github.pull_request.merge"),
            (r"(^|\s)gh\s+release\s+create\b", "github.release.create"),
            (r"(^|\s)(?:wrangler|vercel)\s+deploy\b", "provider.deploy"),
        )
        for pattern, sink in command_sinks:
            if re.search(pattern, stripped):
                effects.append(RawEffect(sink, "external-write", path, line_no))
    return effects, unknowns


def python_effects(
    source: str, *, path: str, line_offset: int = 0
) -> tuple[list[RawEffect], list[UnknownEffect]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], [
            UnknownEffect("PYTHON_SYNTAX_UNKNOWN", path, max(1, line_offset + 1))
        ]
    effects: list[RawEffect] = []
    unknowns: list[UnknownEffect] = []
    if tree.body:
        # The AST recognizers below are evidence extractors, not a complete
        # Python effects proof. Imports, descriptors, aliases, and standard
        # library process APIs can all execute arbitrary behavior.
        unknowns.append(
            UnknownEffect("PYTHON_SOURCE_REVIEW_REQUIRED", path, line_offset + 1)
        )
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                imports[item.asname or item.name.split(".")[0]] = item.name
                if item.name.split(".")[0] not in {
                    "ast", "collections", "datetime", "hashlib", "json", "os",
                    "pathlib", "re", "subprocess", "sys", "tempfile", "typing",
                    "unittest",
                }:
                    unknowns.append(
                        UnknownEffect(
                            "PYTHON_IMPORT_UNRESOLVED",
                            path,
                            line_offset + getattr(node, "lineno", 1),
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for item in node.names:
                imports[item.asname or item.name] = f"{module}.{item.name}"
            if module.split(".")[0] not in {
                "ast", "collections", "datetime", "hashlib", "json", "os",
                "pathlib", "re", "subprocess", "sys", "tempfile", "typing",
                "unittest",
            }:
                unknowns.append(
                    UnknownEffect(
                        "PYTHON_IMPORT_UNRESOLVED",
                        path,
                        line_offset + getattr(node, "lineno", 1),
                    )
                )
        else:
            continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        first, separator, remainder = name.partition(".")
        if first in imports:
            name = imports[first] + (separator + remainder if separator else "")
        tail = name.rsplit(".", 1)[-1]
        line_no = line_offset + getattr(node, "lineno", 1)
        if tail in PYTHON_MUTATORS:
            unknowns.append(
                UnknownEffect("SDK_TARGET_UNRESOLVED", path, line_no)
            )
            effects.append(
                RawEffect(PYTHON_MUTATORS[tail], "external-write", path, line_no)
            )
        if name in {
            "eval", "exec", "compile", "os.system", "getattr",
            "__import__", "importlib.import_module",
        }:
            unknowns.append(UnknownEffect("PYTHON_DYNAMIC_EXECUTION", path, line_no))
        if re.fullmatch(r"(?:requests|httpx)\.(post|put|patch|delete|request)", name):
            unknowns.append(UnknownEffect("HTTP_TARGET_UNRESOLVED", path, line_no))
            verb = name.rsplit(".", 1)[-1]
            if verb != "request":
                effects.append(
                    RawEffect(f"http.{verb}", "external-write", path, line_no)
                )
        elif re.search(r"(?:^|\.)(?:post|put|patch|delete|request)\Z", name):
            unknowns.append(UnknownEffect("PYTHON_CLIENT_UNRESOLVED", path, line_no))
        if tail == "Request" and name.endswith(("urllib.request.Request", "Request")):
            unknowns.append(UnknownEffect("HTTP_TARGET_UNRESOLVED", path, line_no))
            method_node: ast.AST | None = None
            has_data = False
            for keyword in node.keywords:
                if keyword.arg == "method":
                    method_node = keyword.value
                elif keyword.arg == "data":
                    has_data = True
            if method_node is None and has_data:
                effects.append(
                    RawEffect("http.post", "external-write", path, line_no)
                )
            elif (
                isinstance(method_node, ast.Constant)
                and isinstance(method_node.value, str)
            ):
                method = method_node.value.upper()
                if method in MUTATING_HTTP_VERBS:
                    effects.append(
                        RawEffect(
                            f"http.{method.lower()}",
                            "external-write",
                            path,
                            line_no,
                        )
                    )
            elif method_node is not None:
                unknowns.append(
                    UnknownEffect("PYTHON_DYNAMIC_HTTP_METHOD", path, line_no)
                )
        if name in {
            "subprocess.run",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "subprocess.Popen",
            "asyncio.create_subprocess_exec",
            "asyncio.create_subprocess_shell",
        }:
            command = literal_command(node.args[0]) if node.args else None
            if command is None:
                unknowns.append(
                    UnknownEffect("PYTHON_DYNAMIC_SUBPROCESS", path, line_no)
                )
            else:
                nested_effects, nested_unknowns = shell_effects(
                    command, path=path, line_offset=line_no - 1
                )
                effects.extend(nested_effects)
                unknowns.extend(nested_unknowns)
    return effects, unknowns


def inline_python_blocks(
    source: str, *, path: str, start_line: int
) -> tuple[list[RawEffect], list[UnknownEffect]]:
    lines = source.splitlines()
    effects: list[RawEffect] = []
    unknowns: list[UnknownEffect] = []
    index = 0
    while index < len(lines):
        match = re.search(
            r"\bpython3?\s+(?:-\s+)?<<-?['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?",
            lines[index],
        )
        if not match:
            index += 1
            continue
        marker = match.group(1)
        body_start = index + 1
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != marker:
            body.append(lines[index])
            index += 1
        if index >= len(lines):
            unknowns.append(
                UnknownEffect(
                    "UNTERMINATED_PYTHON_HEREDOC", path, start_line + body_start
                )
            )
            break
        nested_effects, nested_unknowns = python_effects(
            "\n".join(body),
            path=path,
            line_offset=start_line + body_start - 1,
        )
        effects.extend(nested_effects)
        unknowns.extend(nested_unknowns)
        index += 1
    return effects, unknowns


def analyze_workflow_source(source: str, *, path: str) -> dict[str, Any]:
    clean = uncommented_yaml(source)
    effects: list[RawEffect] = []
    unknowns: list[UnknownEffect] = []
    if re.search(
        r"(?m)^\s*(?:---|\.\.\.|<<:)|"
        r"^\s*(?:-\s*)?[A-Za-z_][A-Za-z0-9_-]*:\s*[&*][A-Za-z_]",
        clean,
    ):
        unknowns.append(UnknownEffect("YAML_INDIRECTION_UNSUPPORTED", path, 1))
    blocks = run_blocks(clean)
    run_keys = re.findall(r"(?m)^\s*(?:-\s*)?run:\s*", clean)
    if len(run_keys) != len(blocks):
        unknowns.append(UnknownEffect("YAML_RUN_FORM_UNSUPPORTED", path, 1))
    for line_no, line in enumerate(clean.splitlines(), start=1):
        match = re.match(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", line)
        if not match:
            continue
        action = match.group(1)
        if action.startswith("./"):
            unknowns.append(UnknownEffect("LOCAL_ACTION_UNSUPPORTED", path, line_no))
        elif action in KNOWN_ACTION_EFFECTS:
            sink, resource, access = KNOWN_ACTION_EFFECTS[action]
            effects.append(RawEffect(sink, access, path, line_no, resource))
        else:
            unknowns.append(
                UnknownEffect("UNCLASSIFIED_EXTERNAL_ACTION", path, line_no)
            )

    for start_line, block in blocks:
        block_effects, block_unknowns = shell_effects(
            block, path=path, line_offset=start_line - 1
        )
        effects.extend(block_effects)
        unknowns.extend(block_unknowns)
        inline_effects, inline_unknowns = inline_python_blocks(
            block, path=path, start_line=start_line
        )
        effects.extend(inline_effects)
        unknowns.extend(inline_unknowns)

    permissions = workflow_permissions(clean)
    controls = {
        "contents_read": "contents:read" in permissions,
        "no_explicit_secrets": not bool(SECRET_REFERENCE.search(clean)),
        "concurrency": bool(re.search(r"(?m)^concurrency:\s*(?:$|\{)", clean))
        and bool(re.search(r"(?m)^\s+group:\s*\S", clean)),
        "protected_ref": bool(re.search(r"refs/heads/main", clean))
        and bool(re.search(r"(?:GITHUB_REF|github\.ref)", clean)),
        "exact_sha": bool(re.search(r"git\s+rev-parse", clean))
        and bool(re.search(r"(?:GITHUB_SHA|github\.sha|HEAD_SHA)", clean)),
        "expected_before": bool(
            re.search(r"expected[-_ ]before|compare[-_ ]and[-_ ]set", clean, re.I)
        ),
        "readback": bool(re.search(r"read[-_ ]?back|verify.*after", clean, re.I)),
    }
    return {
        "triggers": workflow_triggers(clean),
        "permissions": permissions,
        "credentials": sorted(set(SECRET_REFERENCE.findall(clean))),
        "dependencies": workflow_dependencies(clean),
        "controls": controls,
        "effects": sorted(set(effects)),
        "unknowns": sorted(set(unknowns)),
    }


def git_output(
    root: Path, args: Sequence[str], *, allow_failure: bool = False
) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        timeout=30,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    if completed.returncode != 0 and not allow_failure:
        raise GateError("GIT_READ_FAILED", "could not read the requested Git object")
    return completed.stdout


def resolve_commit(root: Path, revision: str) -> str:
    if not isinstance(revision, str) or not EXACT_SHA.fullmatch(revision):
        raise GateError("REVISION_INVALID", "base/head inputs must be exact 40-hex commits")
    if revision == "0" * 40:
        raise GateError("REVISION_INVALID", "zero is not a Git commit")
    output = git_output(root, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    resolved = output.decode("ascii", errors="strict").strip().lower()
    if not EXACT_SHA.fullmatch(resolved):
        raise GateError("REVISION_INVALID", "base/head must resolve to exact Git commits")
    return resolved


def git_tree(root: Path, revision: str) -> str:
    output = git_output(root, ["rev-parse", "--verify", f"{revision}^{{tree}}"])
    tree = output.decode("ascii", errors="strict").strip()
    if not EXACT_SHA.fullmatch(tree):
        raise GateError("GIT_READ_FAILED", "commit tree is not an exact Git object")
    return tree


def merge_base(root: Path, base: str, head: str) -> str:
    output = git_output(root, ["merge-base", "--all", base, head])
    lines = output.decode("ascii", errors="strict").splitlines()
    if len(lines) != 1 or not EXACT_SHA.fullmatch(lines[0]):
        raise GateError("MERGE_BASE_AMBIGUOUS", "base and head need one exact merge base")
    return lines[0]


def git_object_blob(root: Path, oid: str) -> bytes:
    if not EXACT_SHA.fullmatch(oid):
        raise GateError("GIT_READ_FAILED", "blob identity is invalid")
    return git_output(root, ["cat-file", "blob", oid])


def git_blob(root: Path, revision: str, path: str) -> bytes | None:
    safe = safe_repo_path(path)
    entries = git_output(root, ["ls-tree", "-z", revision, "--", safe]).split(b"\0")
    entries = [item for item in entries if item]
    if not entries:
        return None
    if len(entries) != 1:
        raise GateError("GIT_TREE_INVALID", "path resolves to multiple Git entries")
    match = re.fullmatch(
        rb"([0-7]{6}) (blob|tree|commit) ([0-9a-f]{40})\t(.+)", entries[0]
    )
    if match is None or match.group(4).decode("utf-8", errors="strict") != safe:
        raise GateError("GIT_TREE_INVALID", "Git tree entry is invalid or ambiguous")
    if match.group(1) not in {b"100644", b"100755"} or match.group(2) != b"blob":
        raise GateError("UNSUPPORTED_GIT_MODE", "symlinks and submodules are denied")
    return git_object_blob(root, match.group(3).decode("ascii"))


def git_paths(root: Path, revision: str, prefix: str) -> list[str]:
    output = git_output(
        root, ["ls-tree", "-r", "-z", "--name-only", revision, "--", prefix]
    )
    paths = sorted(
        safe_repo_path(item)
        for item in output.decode("utf-8", errors="strict").split("\0")
        if item
    )
    if len({path.casefold() for path in paths}) != len(paths):
        raise GateError("PATH_COLLISION", "Git tree contains a case-fold path collision")
    return paths


def changed_objects(
    root: Path, base: str, head: str
) -> tuple[list[dict[str, str | None]], str]:
    output = git_output(
        root,
        [
            "diff", "--raw", "-z", "--abbrev=40", "--no-renames",
            "--no-ext-diff", base, head, "--",
        ],
    )
    fields = output.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    if len(fields) % 2:
        raise GateError("GIT_DIFF_INVALID", "Git raw diff is incomplete")
    changes: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for index in range(0, len(fields), 2):
        match = re.fullmatch(
            rb":([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([A-Z])",
            fields[index],
        )
        if match is None:
            raise GateError("GIT_DIFF_INVALID", "Git raw diff entry is unsupported")
        old_mode, new_mode, old_oid, new_oid, status = (
            part.decode("ascii") for part in match.groups()
        )
        path = safe_repo_path(fields[index + 1].decode("utf-8", errors="strict"))
        folded = path.casefold()
        if folded in seen:
            raise GateError("PATH_COLLISION", "change contains a case-fold path collision")
        seen.add(folded)
        for mode in (old_mode, new_mode):
            if mode not in {"000000", "100644", "100755"}:
                raise GateError("UNSUPPORTED_GIT_MODE", "symlinks and submodules are denied")
        if status not in {"A", "C", "D", "M", "T"}:
            raise GateError("GIT_DIFF_INVALID", "Git diff status is unsupported")
        old_blob = None if old_oid == "0" * 40 else old_oid
        new_blob = None if new_oid == "0" * 40 else new_oid
        changes.append(
            {
                "path": path,
                "status": status,
                "old_mode": None if old_mode == "000000" else old_mode,
                "new_mode": None if new_mode == "000000" else new_mode,
                "old_blob": old_blob,
                "new_blob": new_blob,
                "old_sha256": (
                    sha256_bytes(git_object_blob(root, old_blob)) if old_blob else None
                ),
                "new_sha256": (
                    sha256_bytes(git_object_blob(root, new_blob)) if new_blob else None
                ),
            }
        )
    return sorted(changes, key=lambda item: str(item["path"])), sha256_bytes(output)


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    records, _ = changed_objects(root, base, head)
    return [str(item["path"]) for item in records]


def assert_changed_path_uniqueness(
    root: Path, head: str, paths: Sequence[str]
) -> None:
    changed_folded = {path.casefold() for path in paths}
    if not changed_folded:
        return
    tree = git_output(root, ["ls-tree", "-r", "-z", "--name-only", head])
    collisions: Counter[str] = Counter()
    for item in tree.split(b"\0"):
        if not item:
            continue
        folded = item.decode("utf-8", errors="strict").casefold()
        if folded in changed_folded:
            collisions[folded] += 1
    if any(count > 1 for count in collisions.values()):
        raise GateError("PATH_COLLISION", "changed path collides with the Git tree")


def analyze_dependency(
    path: str, content: bytes
) -> tuple[list[RawEffect], list[UnknownEffect]]:
    text = content.decode("utf-8", errors="strict")
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        return python_effects(text, path=path)
    if suffix in {".sh", ".bash", ".ps1"}:
        return shell_effects(text, path=path)
    if suffix == ".json":
        strict_json(content)
        return [], []
    effects: list[RawEffect] = []
    unknowns: list[UnknownEffect] = []
    if text.strip():
        # No JavaScript/TypeScript parser is part of this reviewed grammar.
        # The recognizers below are inventory hints, never an ALLOW proof.
        unknowns.append(UnknownEffect("SCRIPT_SOURCE_REVIEW_REQUIRED", path, 1))
    for line_no, line in enumerate(text.splitlines(), start=1):
        for verb in ("post", "put", "patch", "delete"):
            if re.search(rf"\b(?:axios|client)\.{verb}\s*\(", line):
                effects.append(
                    RawEffect(f"http.{verb}", "external-write", path, line_no)
                )
        if re.search(r"\bfetch\s*\(", line):
            method = re.search(
                r"method\s*:\s*['\"](POST|PUT|PATCH|DELETE)['\"]", line, re.I
            )
            if method:
                effects.append(
                    RawEffect(
                        f"http.{method.group(1).lower()}",
                        "external-write",
                        path,
                        line_no,
                    )
                )
            elif "method" in line:
                unknowns.append(
                    UnknownEffect("JAVASCRIPT_DYNAMIC_HTTP_METHOD", path, line_no)
                )
        if re.search(r"\b(eval|Function)\s*\(", line):
            unknowns.append(
                UnknownEffect("JAVASCRIPT_DYNAMIC_EXECUTION", path, line_no)
            )
    return effects, unknowns


def bind_declaration(
    workflow_path: str,
    source: bytes,
    analysis: dict[str, Any],
    declaration: Mapping[str, Any],
    dependency_blobs: Mapping[str, bytes],
) -> dict[str, Any]:
    reasons: set[str] = set()
    if sha256_bytes(source) != declaration["source_sha256"]:
        reasons.add("WORKFLOW_DIGEST_MISMATCH")
    if analysis["credentials"] != declaration["credentials"]:
        reasons.add("CREDENTIAL_BINDING_MISMATCH")

    required = declaration["required_controls"]
    if not set(required["triggers"]).issubset(analysis["triggers"]):
        reasons.add("REQUIRED_TRIGGER_MISSING")
    for control in (
        "contents_read",
        "no_explicit_secrets",
        "concurrency",
        "protected_ref",
        "exact_sha",
        "expected_before",
        "readback",
    ):
        if required[control] and not analysis["controls"][control]:
            reasons.add(f"CONTROL_{control.upper()}_MISSING")
    if any(permission.endswith(":write") for permission in analysis["permissions"]):
        reasons.add("GITHUB_WRITE_PERMISSION_PRESENT")

    trusted_expected = declaration["trusted_transitives"]
    trusted_observed = {
        path for path in analysis["dependencies"] if path in TRUSTED_TOOL_PATHS
    }
    if trusted_observed != set(trusted_expected):
        reasons.add("TRUSTED_TRANSITIVE_SET_MISMATCH")
    for path, expected_digest in trusted_expected.items():
        content = dependency_blobs.get(path)
        if content is None or sha256_bytes(content) != expected_digest:
            reasons.add("TRUSTED_TRANSITIVE_DIGEST_MISMATCH")

    all_effects = list(analysis["effects"])
    all_unknowns = list(analysis["unknowns"])
    for dependency in analysis["dependencies"]:
        content = dependency_blobs.get(dependency)
        if content is None:
            all_unknowns.append(
                UnknownEffect("LOCAL_DEPENDENCY_MISSING", workflow_path, 1)
            )
            continue
        if dependency in TRUSTED_TOOL_PATHS:
            continue
        dep_effects, dep_unknowns = analyze_dependency(dependency, content)
        all_effects.extend(dep_effects)
        all_unknowns.extend(dep_unknowns)
    all_effects = sorted(set(all_effects))
    all_unknowns = sorted(set(all_unknowns))
    if all_unknowns:
        reasons.add("UNKNOWN_EFFECT")

    declarations = {
        (item["sink"], item["resource"], item["access"]): item
        for item in declaration["effects"]
    }
    counts: Counter[tuple[str, str, str]] = Counter()
    bound_effects: list[dict[str, Any]] = []
    for effect in all_effects:
        candidates = [
            key
            for key in declarations
            if key[0] == effect.sink
            and key[2] == effect.access
            and (not effect.resource or key[1] == effect.resource)
        ]
        if len(candidates) != 1:
            reasons.add(
                "UNDECLARED_EFFECT" if not candidates else "AMBIGUOUS_EFFECT_BINDING"
            )
            continue
        key = candidates[0]
        counts[key] += 1
        bound_effects.append({**effect.public(), "resource": key[1]})
    for key, declared in declarations.items():
        count = counts[key]
        if count == 0:
            reasons.add("OVERBROAD_EFFECT_DECLARATION")
        elif count > declared["max_calls"]:
            reasons.add("MUTATION_BUDGET_EXCEEDED")

    external_writes = sum(
        count for key, count in counts.items() if key[2] == "external-write"
    )
    if external_writes > declaration["max_external_writes"]:
        reasons.add("EXTERNAL_WRITE_BUDGET_EXCEEDED")

    return {
        "workflow": workflow_path,
        "intent_id": declaration["intent_id"],
        "source_sha256": sha256_bytes(source),
        "triggers": analysis["triggers"],
        "permissions": analysis["permissions"],
        "credential_names": analysis["credentials"],
        "controls": analysis["controls"],
        "dependencies": [
            {"path": path, "sha256": sha256_bytes(dependency_blobs[path])}
            for path in analysis["dependencies"]
            if path in dependency_blobs
        ],
        "effects": sorted(
            bound_effects,
            key=lambda item: (
                item["sink"],
                item["resource"],
                item["path"],
                item["line"],
            ),
        ),
        "unknowns": [item.public() for item in all_unknowns],
        "external_write_sites": external_writes,
        "reason_codes": sorted(reasons),
        "verdict": "DENY" if reasons else "ALLOW",
    }


def effect_signature(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(item["sink"]), str(item["resource"]), str(item["access"])


def conflicts(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    claims: dict[str, list[tuple[str, str]]] = {}
    for analysis in analyses:
        for effect in analysis["effects"]:
            claims.setdefault(effect["resource"], []).append(
                (analysis["workflow"], effect["access"])
            )
    found: list[dict[str, Any]] = []
    for resource, resource_claims in sorted(claims.items()):
        workflows = {workflow for workflow, _ in resource_claims}
        if len(workflows) < 2:
            continue
        accesses = {access for _, access in resource_claims}
        if "external-write" in accesses:
            found.append(
                {
                    "resource": resource,
                    "claims": [
                        {"workflow": workflow, "access": access}
                        for workflow, access in sorted(set(resource_claims))
                    ],
                    "code": "CROSS_WORKFLOW_RESOURCE_CONFLICT",
                }
            )
    return found


def analyze_repository(
    root: Path,
    *,
    base_revision: str,
    head_revision: str,
    policy_path: str,
    as_of: date,
) -> dict[str, Any]:
    root = root.resolve()
    if git_output(root, ["rev-parse", "--is-shallow-repository"]).strip() != b"false":
        raise GateError("SHALLOW_REPOSITORY", "complete Git history is required")
    base = resolve_commit(root, base_revision)
    head = resolve_commit(root, head_revision)
    common = merge_base(root, base, head)
    changes, diff_digest = changed_objects(root, common, head)
    paths = [str(item["path"]) for item in changes]
    assert_changed_path_uniqueness(root, head, paths)
    changed_set = set(paths)
    trust_root_changes = sorted(changed_set & TRUST_ROOT_PATHS)
    policy_repo_path = safe_repo_path(policy_path)
    policy_authority = head if trust_root_changes else base
    policy_blob = git_blob(root, policy_authority, policy_repo_path)
    if policy_blob is None:
        raise GateError("POLICY_UNREADABLE", "authority commit lacks the effect policy")
    policy = load_policy_bytes(policy_blob, as_of=as_of)

    head_workflows = [
        path
        for path in git_paths(root, head, ".github/workflows")
        if path.endswith((".yml", ".yaml"))
    ]
    selected: set[str] = {
        path
        for path in paths
        if path.startswith(".github/workflows/")
        and path.endswith((".yml", ".yaml"))
    }
    for workflow in head_workflows:
        blob = git_blob(root, head, workflow)
        if blob is None:
            continue
        dependencies = set(
            workflow_dependencies(blob.decode("utf-8", errors="strict"))
        )
        if dependencies & changed_set:
            selected.add(workflow)
    if policy_repo_path in changed_set:
        selected.update(policy["workflow_declarations"])
    if trust_root_changes:
        selected.update(policy["workflow_declarations"])

    reason_codes: set[str] = set()
    analyses: list[dict[str, Any]] = []
    for workflow in sorted(selected):
        head_blob = git_blob(root, head, workflow)
        if head_blob is None:
            reason_codes.add("WORKFLOW_DELETION_DENIED")
            analyses.append(
                {
                    "workflow": workflow,
                    "verdict": "DENY",
                    "reason_codes": ["WORKFLOW_DELETION_DENIED"],
                    "effects": [],
                    "unknowns": [],
                }
            )
            continue
        declaration = policy["workflow_declarations"].get(workflow)
        if declaration is None:
            reason_codes.add("WORKFLOW_DECLARATION_MISSING")
            analyses.append(
                {
                    "workflow": workflow,
                    "source_sha256": sha256_bytes(head_blob),
                    "verdict": "DENY",
                    "reason_codes": ["WORKFLOW_DECLARATION_MISSING"],
                    "effects": [],
                    "unknowns": [],
                }
            )
            continue
        source = head_blob.decode("utf-8", errors="strict")
        raw = analyze_workflow_source(source, path=workflow)
        dependencies: dict[str, bytes] = {}
        for dependency in raw["dependencies"]:
            blob = git_blob(root, head, dependency)
            if blob is not None:
                dependencies[dependency] = blob
        analysis = bind_declaration(
            workflow, head_blob, raw, declaration, dependencies
        )

        base_blob = git_blob(root, common, workflow)
        base_effects: set[tuple[str, str, str]] = set()
        if base_blob is not None:
            base_raw = analyze_workflow_source(
                base_blob.decode("utf-8", errors="strict"), path=workflow
            )
            base_effects = {
                (effect.sink, effect.resource, effect.access)
                for effect in base_raw["effects"]
                if effect.resource
            }
        head_effects = {effect_signature(effect) for effect in analysis["effects"]}
        analysis["delta"] = {
            "added": [
                {"sink": sink, "resource": resource, "access": access}
                for sink, resource, access in sorted(head_effects - base_effects)
            ],
            "removed": [
                {"sink": sink, "resource": resource, "access": access}
                for sink, resource, access in sorted(base_effects - head_effects)
            ],
        }
        analyses.append(analysis)
        reason_codes.update(analysis["reason_codes"])

    conflict_records = conflicts(analyses)
    if conflict_records:
        reason_codes.add("CROSS_WORKFLOW_RESOURCE_CONFLICT")
    covered_paths = set(selected)
    for analysis in analyses:
        covered_paths.update(
            item["path"] for item in analysis.get("dependencies", [])
        )
    executable_prefixes = (
        ".github/scripts/",
        ".github/actions/",
        ".github/data/",
        ".github/workflows/",
        "scripts/",
        "tools/",
        "actions/",
    )
    unbound_executable_changes = sorted(
        path
        for path in paths
        if path.startswith(executable_prefixes)
        and path not in covered_paths
        and path not in TRUST_ROOT_PATHS
    )
    if unbound_executable_changes:
        reason_codes.add("UNBOUND_EXECUTABLE_CHANGE")
    hard_reasons = {
        "WORKFLOW_DELETION_DENIED",
        "WORKFLOW_DECLARATION_MISSING",
        "WORKFLOW_DIGEST_MISMATCH",
        "TRUSTED_TRANSITIVE_DIGEST_MISMATCH",
        "TRUSTED_TRANSITIVE_SET_MISMATCH",
    }
    if reason_codes & hard_reasons:
        verdict = "DENY"
    elif trust_root_changes:
        reason_codes.add("TRUST_ROOT_CHANGED_REVIEW_REQUIRED")
        verdict = "REVIEW_REQUIRED"
    elif reason_codes:
        verdict = "DENY"
    else:
        verdict = "ALLOW"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "base_revision": base,
        "head_revision": head,
        "merge_base": common,
        "base_tree": git_tree(root, base),
        "head_tree": git_tree(root, head),
        "diff_sha256": diff_digest,
        "checker": {
            "path": ".github/scripts/control_plane_effect_gate.py",
            "base_sha256": (
                sha256_bytes(base_checker)
                if (base_checker := git_blob(
                    root, base, ".github/scripts/control_plane_effect_gate.py"
                )) is not None
                else None
            ),
            "head_sha256": (
                sha256_bytes(head_checker)
                if (head_checker := git_blob(
                    root, head, ".github/scripts/control_plane_effect_gate.py"
                )) is not None
                else None
            ),
        },
        "policy": {
            "path": policy_repo_path,
            "authority_revision": policy_authority,
            "sha256": policy["_sha256"],
            "schema": policy["schema"],
            "valid_from": policy["valid_from"],
            "valid_until": policy["valid_until"],
        },
        "changed_paths": paths,
        "changed_objects": changes,
        "trust_root_changes": trust_root_changes,
        "unbound_executable_changes": unbound_executable_changes,
        "analyses": analyses,
        "conflicts": conflict_records,
        "reason_codes": sorted(reason_codes),
        "verdict": verdict,
        "claim": (
            (
                "VERIFIED_STATIC_EFFECT_BOUNDARY"
                if selected
                else "NO_DECLARED_CONTROL_PLANE_EFFECT_CHANGE"
            )
            if verdict == "ALLOW"
            else (
                "TRUST_ROOT_CHANGED_REVIEW_REQUIRED"
                if verdict == "REVIEW_REQUIRED"
                else "DENIED_STATIC_EFFECT_BOUNDARY"
            )
        ),
        "claim_limit": (
            "Bounded reviewed grammar only; no arbitrary-program formal proof."
        ),
        "provider_calls_performed": False,
        "secret_values_requested": False,
        "secret_values_recorded": False,
    }
    receipt["decision_digest"] = sha256_bytes(canonical_bytes(receipt))
    return receipt


def failure_receipt(base: str, head: str, exc: Exception) -> dict[str, Any]:
    code = exc.code if isinstance(exc, GateError) else "INTERNAL_ANALYZER_FAILURE"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "base_revision": base if EXACT_SHA.fullmatch(base) else "UNRESOLVED",
        "head_revision": head if EXACT_SHA.fullmatch(head) else "UNRESOLVED",
        "analyses": [],
        "conflicts": [],
        "reason_codes": [code],
        "verdict": "DENY",
        "claim": "DENIED_STATIC_EFFECT_BOUNDARY",
        "claim_limit": (
            "Bounded reviewed grammar only; no arbitrary-program formal proof."
        ),
        "provider_calls_performed": False,
        "secret_values_requested": False,
        "secret_values_recorded": False,
    }
    receipt["decision_digest"] = sha256_bytes(canonical_bytes(receipt))
    return receipt


def write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".control-plane-effect-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    try:
        receipt = analyze_repository(
            args.repository_root,
            base_revision=args.base,
            head_revision=args.head,
            policy_path=args.policy,
            as_of=args.as_of,
        )
    except Exception as exc:
        receipt = failure_receipt(args.base, args.head, exc)
    write_receipt(args.report, receipt)
    sys.stdout.buffer.write(canonical_bytes(receipt))
    return {"ALLOW": 0, "DENY": 2, "REVIEW_REQUIRED": 3}[receipt["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
