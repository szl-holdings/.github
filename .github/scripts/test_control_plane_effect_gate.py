#!/usr/bin/env python3
"""Adversarial, network-free tests for the bounded control-plane effect gate."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


CHECKER_PATH = Path(__file__).with_name("control_plane_effect_gate.py")
SPEC = importlib.util.spec_from_file_location("control_plane_effect_gate", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

AS_OF = date(2026, 9, 24)
WORKFLOW_PATH = ".github/workflows/fixture.yml"
POLICY_PATH = ".github/data/control_plane_effect_policy.json"
CHECKER_REPO_PATH = ".github/scripts/control_plane_effect_gate.py"
CHECKOUT_ACTION = (
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
)
CHECKOUT_RESOURCE = "github:repository:szl-holdings/.github:contents"
UPLOAD_ACTION = (
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
)


def workflow(*, name: str = "fixture", extra_step: str = "") -> bytes:
    return (
        f'name: {name}\n'
        '"on": [pull_request, merge_group, push]\n'
        "permissions:\n"
        "  contents: read\n"
        "concurrency:\n"
        "  group: fixture\n"
        "jobs:\n"
        "  fixture:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        f"      - uses: {CHECKOUT_ACTION}\n"
        f"{extra_step}"
    ).encode("utf-8")


def policy_for(
    source: bytes,
    *,
    workflow_path: str = WORKFLOW_PATH,
    credentials: list[str] | None = None,
    extra_resources: list[dict[str, str]] | None = None,
    extra_effects: list[dict[str, object]] | None = None,
    max_external_writes: int = 0,
) -> dict[str, object]:
    return {
        "schema": gate.POLICY_SCHEMA,
        "valid_from": "2026-08-30",
        "valid_until": "2026-11-30",
        "default_decision": "deny",
        "unknown_effect": "deny",
        "wildcard_resources": "deny",
        "workflow_declarations": {
            workflow_path: {
                "intent_id": "fixture-effect-contract-v1",
                "valid_until": "2026-11-30",
                "source_sha256": gate.sha256_bytes(source),
                "credentials": credentials or [],
                "resources": [
                    {"key": CHECKOUT_RESOURCE, "access": "read"},
                    *(extra_resources or []),
                ],
                "effects": [
                    {
                        "sink": "github.contents.checkout",
                        "resource": CHECKOUT_RESOURCE,
                        "access": "read",
                        "max_calls": 1,
                    },
                    *(extra_effects or []),
                ],
                "max_external_writes": max_external_writes,
                "required_controls": {
                    "triggers": ["pull_request", "merge_group", "push"],
                    "contents_read": True,
                    "no_explicit_secrets": credentials is None,
                    "concurrency": True,
                    "protected_ref": False,
                    "exact_sha": False,
                    "expected_before": False,
                    "readback": False,
                },
                "trusted_transitives": {},
            }
        },
    }


def policy_bytes(policy: dict[str, object]) -> bytes:
    return (json.dumps(policy, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


class TemporaryRepository:
    """A two-commit Git fixture with no remotes or global identity dependency."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="cp-ebom-test-")
        self.root = Path(self._temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.filemode", "true")
        self.git("config", "commit.gpgsign", "false")

    def __enter__(self) -> TemporaryRepository:
        return self

    def __exit__(self, *_args: object) -> None:
        self._temporary.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.stdout.strip()

    def write(self, path: str, data: bytes) -> None:
        target = self.root.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def install_baseline(self, source: bytes | None = None) -> str:
        content = source or workflow()
        self.write(WORKFLOW_PATH, content)
        self.write(POLICY_PATH, policy_bytes(policy_for(content)))
        return self.commit("fixture baseline")


def analyze(root: Path, base: str, head: str) -> dict[str, object]:
    return gate.analyze_repository(
        root,
        base_revision=base,
        head_revision=head,
        policy_path=POLICY_PATH,
        as_of=AS_OF,
    )


def bind_source(
    source: bytes,
    *,
    candidate: dict[str, object] | None = None,
    dependencies: dict[str, bytes] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Exercise analysis with a policy bound to the actual adversarial source."""
    declaration = gate.load_policy_bytes(
        policy_bytes(candidate or policy_for(source)), as_of=AS_OF
    )["workflow_declarations"][WORKFLOW_PATH]
    parsed = gate.analyze_workflow_source(source.decode("utf-8"), path=WORKFLOW_PATH)
    bound = gate.bind_declaration(
        WORKFLOW_PATH, source, parsed, declaration, dependencies or {}
    )
    return parsed, bound


def reviewed_policy_for(
    source: bytes,
    *,
    dependencies: dict[str, bytes] | None = None,
    credentials: list[str] | None = None,
) -> dict[str, object]:
    """Pin the observed unknown set so denials cannot depend on missing review."""
    candidate = policy_for(source, credentials=credentials)
    parsed = gate.analyze_workflow_source(source.decode("utf-8"), path=WORKFLOW_PATH)
    unknowns = list(parsed["unknowns"])
    for path, content in (dependencies or {}).items():
        _effects, dependency_unknowns = gate.analyze_dependency(path, content)
        unknowns.extend(dependency_unknowns)
    files = {WORKFLOW_PATH: gate.sha256_bytes(source)}
    files.update({path: gate.sha256_bytes(content) for path, content in (dependencies or {}).items()})
    candidate["workflow_declarations"][WORKFLOW_PATH]["reviewed_unknowns"] = {
        "files": files,
        "unknowns": sorted({f"{item.code}@{item.path}:{item.line}" for item in unknowns}),
    }
    return candidate


class PolicyAndPathTests(unittest.TestCase):
    def assert_gate_code(self, expected: str, function: object) -> None:
        with self.assertRaises(gate.GateError) as raised:
            function()
        self.assertEqual(raised.exception.code, expected)

    def test_policy_duplicate_key_is_rejected_even_when_values_match(self) -> None:
        self.assert_gate_code(
            "POLICY_DUPLICATE_KEY",
            lambda: gate.strict_json(b'{"schema":"one","schema":"one"}'),
        )

    def test_policy_nonfinite_numbers_are_rejected(self) -> None:
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(value=value):
                self.assert_gate_code(
                    "POLICY_NONFINITE_NUMBER",
                    lambda: gate.strict_json(b'{"budget":' + value + b"}"),
                )

    def test_policy_unknown_key_cannot_extend_authority(self) -> None:
        candidate = policy_for(workflow())
        candidate["ignore_paths"] = ["**"]
        self.assert_gate_code(
            "POLICY_SCHEMA_INVALID",
            lambda: gate.load_policy_bytes(policy_bytes(candidate), as_of=AS_OF),
        )

    def test_wildcard_resource_is_rejected(self) -> None:
        candidate = policy_for(workflow())
        declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
        declaration["resources"][0]["key"] = "github:*"
        self.assert_gate_code(
            "WILDCARD_RESOURCE_DENIED",
            lambda: gate.load_policy_bytes(policy_bytes(candidate), as_of=AS_OF),
        )

    def test_path_normalization_is_never_silent(self) -> None:
        for unsafe in (
            "../outside.yml",
            ".github/../outside.yml",
            "./.github/workflows/fixture.yml",
            ".github//workflows/fixture.yml",
            ".github\\workflows\\fixture.yml",
            "/absolute/fixture.yml",
            "C:/absolute/fixture.yml",
            ".github/workflows/cafe\u0301.yml",
            ".github/workflows/fixture.yml\x00",
        ):
            with self.subTest(unsafe=repr(unsafe)):
                self.assert_gate_code(
                    "UNSAFE_PATH", lambda: gate.safe_repo_path(unsafe)
                )

    def test_commit_inputs_require_full_lowercase_object_ids(self) -> None:
        with TemporaryRepository() as fixture:
            commit = fixture.install_baseline()
            for unsafe in ("HEAD", commit[:12], commit.upper(), "0" * 40):
                with self.subTest(revision=unsafe):
                    self.assert_gate_code(
                        "REVISION_INVALID",
                        lambda: gate.resolve_commit(fixture.root, unsafe),
                    )
            self.assertEqual(gate.resolve_commit(fixture.root, commit), commit)


class SinkRecognitionTests(unittest.TestCase):
    def test_local_json_path_is_not_truncated_to_javascript(self) -> None:
        source = "python gate.py --policy .github/data/control_plane_effect_policy.json"
        self.assertEqual(
            gate.workflow_dependencies(source),
            [".github/data/control_plane_effect_policy.json"],
        )

    def test_github_local_uses_prefix_resolves_to_one_git_path(self) -> None:
        self.assertEqual(
            gate.workflow_dependencies(
                "uses: ./.github/workflows/reusable-production-readiness.yml"
            ),
            [".github/workflows/reusable-production-readiness.yml"],
        )

    def test_unclassified_shell_commands_cannot_earn_allow(self) -> None:
        for command in (
            "aws s3 cp artifact s3://bucket/key",
            "wget --post-data=data https://example.invalid/write",
            "bash -c true",
        ):
            with self.subTest(command=command):
                _effects, unknowns = gate.shell_effects(
                    command, path="scripts/fixture.sh"
                )
                self.assertIn(
                    "SHELL_COMMAND_UNCLASSIFIED",
                    {item.code for item in unknowns},
                )

    def test_unclassified_python_process_api_cannot_earn_allow(self) -> None:
        _effects, unknowns = gate.python_effects(
            "import os\nos.popen(123)\n", path="scripts/fixture.py"
        )
        self.assertIn(
            "PYTHON_SOURCE_REVIEW_REQUIRED",
            {item.code for item in unknowns},
        )

    def test_unparsed_javascript_dependency_cannot_earn_allow(self) -> None:
        _effects, unknowns = gate.analyze_dependency(
            "scripts/fixture.js",
            b"fetch(url, {\n  method: 'POST'\n})\n",
        )
        self.assertIn(
            "SCRIPT_SOURCE_REVIEW_REQUIRED",
            {item.code for item in unknowns},
        )

    def test_known_action_has_exact_read_effect(self) -> None:
        observed = gate.analyze_workflow_source(
            workflow().decode("utf-8"), path=WORKFLOW_PATH
        )
        self.assertEqual(
            [(item.sink, item.resource, item.access) for item in observed["effects"]],
            [("github.contents.checkout", CHECKOUT_RESOURCE, "read")],
        )
        self.assertEqual(observed["unknowns"], [])

    def test_unknown_and_local_actions_fail_closed(self) -> None:
        source = workflow(
            extra_step=(
                "      - uses: unreviewed/action@"
                + "a" * 40
                + "\n"
                "      - uses: ./.github/actions/local\n"
            )
        )
        observed = gate.analyze_workflow_source(
            source.decode("utf-8"), path=WORKFLOW_PATH
        )
        codes = {item.code for item in observed["unknowns"]}
        self.assertIn("UNCLASSIFIED_EXTERNAL_ACTION", codes)
        self.assertIn("LOCAL_ACTION_UNSUPPORTED", codes)

    def test_shell_dynamic_method_and_eval_are_unknown(self) -> None:
        _effects, unknowns = gate.shell_effects(
            'curl -X "$METHOD" https://example.invalid/api\n'
            'eval "$NEXT_COMMAND"\n',
            path="scripts/fixture.sh",
        )
        codes = {item.code for item in unknowns}
        self.assertIn("CURL_DYNAMIC_METHOD", codes)
        self.assertIn("DYNAMIC_EXECUTION", codes)

    def test_shell_upload_shorthand_is_an_external_write(self) -> None:
        effects, unknowns = gate.shell_effects(
            "curl --data payload https://example.invalid/api",
            path="scripts/fixture.sh",
        )
        self.assertIn(
            "HTTP_TARGET_UNRESOLVED", {item.code for item in unknowns}
        )
        self.assertEqual(
            [(effect.sink, effect.access) for effect in effects],
            [("http.post", "external-write")],
        )

    def test_python_mutator_and_dynamic_subprocess(self) -> None:
        effects, unknowns = gate.python_effects(
            "api.update_repo_settings(repo_id='SZLHOLDINGS/demo')\n"
            "subprocess.run(command, check=True)\n",
            path="scripts/fixture.py",
        )
        self.assertIn(
            ("sdk.huggingface.update_repo_settings", "external-write"),
            {(effect.sink, effect.access) for effect in effects},
        )
        self.assertIn(
            "PYTHON_DYNAMIC_SUBPROCESS", {item.code for item in unknowns}
        )

    def test_dynamic_python_http_method_is_not_a_read(self) -> None:
        _effects, unknowns = gate.python_effects(
            "requests.request(method, url)\n",
            path="scripts/fixture.py",
        )
        self.assertTrue(unknowns)

    def test_alias_import_cannot_launder_python_post(self) -> None:
        effects, unknowns = gate.python_effects(
            "from requests import post as send\nsend(url, data=payload)\n",
            path="scripts/fixture.py",
        )
        self.assertTrue(
            effects or unknowns,
            "an aliased HTTP call must be classified or explicitly unknown",
        )

    def test_python_heredoc_mutation_is_detected(self) -> None:
        source = workflow(
            extra_step=(
                "      - run: |\n"
                "          python <<'PY'\n"
                "          import requests\n"
                "          requests.post('https://example.invalid/api')\n"
                "          PY\n"
            )
        )
        observed = gate.analyze_workflow_source(
            source.decode("utf-8"), path=WORKFLOW_PATH
        )
        self.assertTrue(
            "http.post" in {effect.sink for effect in observed["effects"]}
            or observed["unknowns"],
            "inline Python must be classified as a write or fail closed as unknown",
        )

    def test_isolated_inline_python_keeps_effect_inventory(self) -> None:
        legacy = (
            "python <<'PY'\nimport requests\n"
            "requests.post('https://example.invalid/api')\nPY\n"
        )
        isolated = legacy.replace("python ", "python -I ", 1)
        legacy_effects, legacy_unknowns = gate.inline_python_blocks(legacy, path=WORKFLOW_PATH, start_line=1)
        effects, unknowns = gate.inline_python_blocks(isolated, path=WORKFLOW_PATH, start_line=1)
        self.assertIn(("http.post", "external-write"), {(item.sink, item.access) for item in effects})
        self.assertEqual(effects, legacy_effects)
        self.assertEqual(unknowns, legacy_unknowns)


class DeclarationTests(unittest.TestCase):
    def test_generic_http_endpoint_cannot_be_bound_to_arbitrary_resource(self) -> None:
        source = workflow(
            extra_step=(
                "      - run: curl -X POST https://example.invalid/elsewhere\n"
            )
        )
        candidate = policy_for(
            source,
            extra_resources=[
                {"key": "huggingface:space:SZLHOLDINGS/approved", "access": "external-write"}
            ],
            extra_effects=[
                {
                    "sink": "http.post",
                    "resource": "huggingface:space:SZLHOLDINGS/approved",
                    "access": "external-write",
                    "max_calls": 1,
                }
            ],
            max_external_writes=1,
        )
        declaration = gate.load_policy_bytes(
            policy_bytes(candidate), as_of=AS_OF
        )["workflow_declarations"][WORKFLOW_PATH]
        parsed = gate.analyze_workflow_source(
            source.decode("utf-8"), path=WORKFLOW_PATH
        )
        bound = gate.bind_declaration(WORKFLOW_PATH, source, parsed, declaration, {})
        self.assertEqual(bound["verdict"], "DENY")
        self.assertTrue(bound["reason_codes"])

    def test_unbudgeted_effect_is_denied(self) -> None:
        source = workflow(extra_step="      - run: git push origin main\n")
        declaration = gate.load_policy_bytes(
            policy_bytes(policy_for(source)), as_of=AS_OF
        )["workflow_declarations"][WORKFLOW_PATH]
        parsed = gate.analyze_workflow_source(
            source.decode("utf-8"), path=WORKFLOW_PATH
        )
        bound = gate.bind_declaration(WORKFLOW_PATH, source, parsed, declaration, {})
        self.assertEqual(bound["verdict"], "DENY")
        self.assertIn("UNDECLARED_EFFECT", bound["reason_codes"])

    def test_extra_declared_effect_is_overbroad(self) -> None:
        source = workflow()
        candidate = policy_for(
            source,
            extra_resources=[
                {"key": "github:release:fixture", "access": "external-write"}
            ],
            extra_effects=[
                {
                    "sink": "github.release.create",
                    "resource": "github:release:fixture",
                    "access": "external-write",
                    "max_calls": 1,
                }
            ],
        )
        declaration = gate.load_policy_bytes(
            policy_bytes(candidate), as_of=AS_OF
        )["workflow_declarations"][WORKFLOW_PATH]
        parsed = gate.analyze_workflow_source(
            source.decode("utf-8"), path=WORKFLOW_PATH
        )
        bound = gate.bind_declaration(WORKFLOW_PATH, source, parsed, declaration, {})
        self.assertEqual(bound["verdict"], "DENY")
        self.assertIn("OVERBROAD_EFFECT_DECLARATION", bound["reason_codes"])

    def test_conflicting_external_writers_are_named(self) -> None:
        effect = {
            "sink": "http.post",
            "resource": "huggingface:space:SZLHOLDINGS/fixture",
            "access": "external-write",
        }
        found = gate.conflicts(
            [
                {"workflow": ".github/workflows/a.yml", "effects": [copy.copy(effect)]},
                {"workflow": ".github/workflows/b.yml", "effects": [copy.copy(effect)]},
            ]
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["code"], "CROSS_WORKFLOW_RESOURCE_CONFLICT")


class YamlBoundaryRegressionTests(unittest.TestCase):
    def assert_source_denied(
        self,
        source: bytes,
        *,
        reason: str,
        candidate: dict[str, object] | None = None,
        dependencies: dict[str, bytes] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        parsed, bound = bind_source(source, candidate=candidate, dependencies=dependencies)
        self.assertEqual(bound["source_sha256"], gate.sha256_bytes(source))
        self.assertNotIn("WORKFLOW_DIGEST_MISMATCH", bound["reason_codes"])
        self.assertEqual(bound["verdict"], "DENY")
        self.assertIn(reason, bound["reason_codes"])
        return parsed, bound

    def test_same_line_flow_checkouts_preserve_distinct_call_occurrences(self) -> None:
        prefix = workflow().decode().split("jobs:\n", 1)[0]
        checkout = f"{{uses: {CHECKOUT_ACTION}}}"
        for jobs in (
            f"jobs: {{fixture: {{runs-on: ubuntu-latest, steps: [{checkout}, {checkout}]}}}}\n",
            "jobs: {"
            + ", ".join(
                f"{name}: {{runs-on: ubuntu-latest, steps: [{checkout}]}}"
                for name in ("first", "second")
            ) + "}\n",
        ):
            with self.subTest(jobs=jobs):
                source = (prefix + jobs).encode()
                candidate = policy_for(source)
                parsed, bound = self.assert_source_denied(
                    source, reason="MUTATION_BUDGET_EXCEEDED", candidate=candidate
                )
                self.assertEqual(parsed["unknowns"], [])
                self.assertEqual(len(parsed["effects"]), 2)
                self.assertEqual(parsed["effects"][0], parsed["effects"][1])
                self.assertEqual(len(bound["effects"]), 2)
                # A sufficient fixture budget verifies that flow YAML remains supported.
                candidate["workflow_declarations"][WORKFLOW_PATH]["effects"][0]["max_calls"] = 2
                _parsed, allowed = bind_source(source, candidate=candidate)
                self.assertEqual(allowed["verdict"], "ALLOW")

    def test_same_line_flow_run_mutations_preserve_external_write_occurrences(self) -> None:
        prefix = workflow().decode().split("    steps:\n", 1)[0]
        command = "curl -X POST https://example.invalid/api"
        source = (
            prefix + f"    steps: [{{uses: {CHECKOUT_ACTION}}}, "
            + f"{{run: {json.dumps(command)}}}, {{run: {json.dumps(command)}}}]\n"
        ).encode()
        candidate = reviewed_policy_for(source)
        declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
        resource = "https:example.invalid/api"
        declaration["resources"].append({"key": resource, "access": "external-write"})
        declaration["effects"].append({
            "sink": "http.post", "resource": resource,
            "access": "external-write", "max_calls": 1,
        })
        declaration["max_external_writes"] = 1
        parsed, bound = self.assert_source_denied(
            source, reason="MUTATION_BUDGET_EXCEEDED", candidate=candidate
        )
        posts = [effect for effect in parsed["effects"] if effect.sink == "http.post"]
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0], posts[1])
        self.assertTrue(bound["reviewed_unknowns_applied"])
        self.assertIn("EXTERNAL_WRITE_BUDGET_EXCEEDED", bound["reason_codes"])
        self.assertEqual(bound["external_write_sites"], 2)
        declaration["effects"][-1]["max_calls"] = 2
        declaration["max_external_writes"] = 2
        _parsed, allowed = bind_source(source, candidate=candidate)
        self.assertEqual(allowed["verdict"], "ALLOW")

    def test_binding_preserves_same_line_dependency_call_occurrences(self) -> None:
        source = workflow(extra_step="      - run: python scripts/fixture.py\n")
        dependencies = {
            "scripts/fixture.py": (
                b"import requests\n"
                b"requests.post('https://example.invalid/api'); "
                b"requests.post('https://example.invalid/api')\n"
            )
        }
        candidate = reviewed_policy_for(source, dependencies=dependencies)
        declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
        resource = "https:example.invalid/api"
        declaration["resources"].append({"key": resource, "access": "external-write"})
        declaration["effects"].append({
            "sink": "http.post", "resource": resource,
            "access": "external-write", "max_calls": 1,
        })
        declaration["max_external_writes"] = 1
        _parsed, bound = self.assert_source_denied(
            source, reason="MUTATION_BUDGET_EXCEEDED", candidate=candidate,
            dependencies=dependencies,
        )
        self.assertTrue(bound["reviewed_unknowns_applied"])
        self.assertEqual(bound["external_write_sites"], 2)
        self.assertIn("EXTERNAL_WRITE_BUDGET_EXCEEDED", bound["reason_codes"])
        declaration["effects"][-1]["max_calls"] = 2
        declaration["max_external_writes"] = 2
        _parsed, allowed = bind_source(source, candidate=candidate, dependencies=dependencies)
        self.assertEqual(allowed["verdict"], "ALLOW")

    def test_run_spellings_and_decoded_commands_cannot_hide_git_push(self) -> None:
        for step in (
            "      - run : git push origin main\n",
            "      - 'run': git push origin main\n",
            '      - "run": git push origin main\n',
            '      - "r\\u0075n": git push origin main\n',
            "      - {run: git push origin main}\n",
            '      - {"r\\u0075n": "git \\u0070ush origin main"}\n',
        ):
            with self.subTest(step=step):
                source = workflow(extra_step=step)
                parsed, _bound = self.assert_source_denied(source, reason="UNDECLARED_EFFECT")
                self.assertIn(
                    ("git.remote.push", "external-write"),
                    {(item.sink, item.access) for item in parsed["effects"]},
                )
                self.assertEqual(gate.run_blocks(source.decode("utf-8"))[0][1], "git push origin main")

    def test_uses_spellings_cannot_hide_known_external_action(self) -> None:
        for key in ("uses ", "'uses'", '"uses"', '"u\\u0073es"'):
            for flow in (False, True):
                with self.subTest(key=key, flow=flow):
                    entry = f"{key}: {UPLOAD_ACTION}"
                    source = workflow(extra_step="      - " + ("{" + entry + "}" if flow else entry) + "\n")
                    parsed, _bound = self.assert_source_denied(source, reason="UNDECLARED_EFFECT")
                    self.assertIn(
                        ("github.artifact.upload", "external-write"),
                        {(item.sink, item.access) for item in parsed["effects"]},
                    )

    def test_supported_yaml_spellings_keep_known_checkout_boundary(self) -> None:
        for checkout in (
            f"      - uses : {CHECKOUT_ACTION}\n",
            f"      - 'uses': '{CHECKOUT_ACTION}'\n",
            f'      - "u\\u0073es": "{CHECKOUT_ACTION}"\n',
            f"      - {{uses: {CHECKOUT_ACTION}}}\n",
        ):
            with self.subTest(checkout=checkout):
                source = workflow().replace(f"      - uses: {CHECKOUT_ACTION}\n".encode(), checkout.encode())
                source = source.replace(b'"on":', b"on:")
                parsed, bound = bind_source(source)
                self.assertEqual(parsed["triggers"], ["merge_group", "pull_request", "push"])
                self.assertEqual(parsed["unknowns"], [])
                self.assertEqual(bound["verdict"], "ALLOW")
                self.assertEqual(bound["effects"][0]["resource"], CHECKOUT_RESOURCE)

    def test_inline_and_write_all_permissions_cannot_hide_write_authority(self) -> None:
        for root_permission, job_permission, expected in (
            ("permissions: {contents: read, actions: write}\n", "", "actions:write"),
            ('"permi\\u0073sions": {contents: read, issues: write}\n', "", "issues:write"),
            ("permissions: write-all\n", "", "*:write"),
            ("permissions:\n  contents: read\n", "    permissions: {contents: read, id-token: write}\n", "id-token:write"),
            ("permissions:\n  contents: read\n", "    'permissions': write-all\n", "*:write"),
        ):
            with self.subTest(root=root_permission, job=job_permission):
                source = workflow().replace(b"permissions:\n  contents: read\n", root_permission.encode())
                source = source.replace(b"    steps:\n", job_permission.encode() + b"    steps:\n")
                parsed, _bound = self.assert_source_denied(source, reason="GITHUB_WRITE_PERMISSION_PRESENT")
                self.assertIn(expected, parsed["permissions"])

    def test_read_all_permissions_are_recognized_as_read(self) -> None:
        source = workflow().replace(b"permissions:\n  contents: read\n", b"permissions: read-all\n")
        parsed, bound = bind_source(source)
        self.assertEqual(parsed["permissions"], ["*:read"])
        self.assertEqual(bound["verdict"], "ALLOW")

    def test_secret_fallback_bracket_and_aggregate_expressions_are_detected(self) -> None:
        expressions = (
            ("secrets.HF_TOKEN || 'placeholder'", ["HF_TOKEN"], False),
            ("secrets['HF_TOKEN']", ["HF_TOKEN"], False),
            ("SeCrEtS['HF_TOKEN']", ["HF_TOKEN"], False),
            ("secrets[format('HF_{0}', 'TOKEN')]", [], True),
            ("toJSON(secrets)", [], True),
            ("github.token", ["GITHUB_TOKEN"], False),
            ("github['token']", ["GITHUB_TOKEN"], False),
            ('GITHUB["TOKEN"]', ["GITHUB_TOKEN"], False),
        )
        for expression, names, unresolved in expressions:
            with self.subTest(expression=expression):
                value = "$" + "{{ " + expression + " }}"
                source = workflow(extra_step="      - run: true\n        env:\n          FIXTURE_AUTH: " + json.dumps(value) + "\n")
                candidate = policy_for(source, credentials=names)
                parsed, _bound = self.assert_source_denied(source, reason="UNKNOWN_EFFECT", candidate=candidate)
                self.assertEqual(parsed["credentials"], names)
                self.assertFalse(parsed["controls"]["no_explicit_secrets"])
                self.assertIn("SECRET_EXPRESSION_REVIEW_REQUIRED", {item.code for item in parsed["unknowns"]})
                if unresolved:
                    reviewed = reviewed_policy_for(source, credentials=names)
                    self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=reviewed)

    def test_mixed_literal_and_dynamic_github_indexes_cannot_hide_possible_token(self) -> None:
        expression = "$" + "{{ github['ref'] && github[inputs.key] }}"
        source = workflow(extra_step="      - run: true\n        env:\n          FIXTURE_AUTH: " + json.dumps(expression) + "\n")
        candidate = reviewed_policy_for(source, credentials=[])
        parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
        self.assertEqual(parsed["credentials"], [])
        self.assertFalse(parsed["controls"]["no_explicit_secrets"])
        self.assertIn("SECRET_NAME_UNRESOLVED", {item.code for item in parsed["unknowns"]})
        self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_execution_contexts_cannot_be_waived_with_exact_unknown_pins(self) -> None:
        for addition, expected in (
            ("    services: {fixture: {image: 'example.invalid/fixture:latest'}}\n", "CONTAINER_EXECUTION_UNSUPPORTED"),
            ("    'services':\n      fixture:\n        image: example.invalid/fixture:latest\n", "CONTAINER_EXECUTION_UNSUPPORTED"),
            ("    container: example.invalid/fixture:latest\n", "CONTAINER_EXECUTION_UNSUPPORTED"),
            ('    "conta\\u0069ner": {image: "example.invalid/fixture:latest"}\n', "CONTAINER_EXECUTION_UNSUPPORTED"),
            ("    strategy: {matrix: {lane: [one, two]}}\n", "WORKFLOW_FANOUT_UNSUPPORTED"),
            ('    "stra\\u0074egy":\n      matrix:\n        lane: [one, two]\n', "WORKFLOW_FANOUT_UNSUPPORTED"),
        ):
            with self.subTest(addition=addition):
                source = workflow().replace(b"    steps:\n", addition.encode() + b"    steps:\n")
                candidate = reviewed_policy_for(source)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertIn(expected, {item.code for item in parsed["unknowns"]})
                self.assertIn("UNKNOWN_EFFECT", bound["reason_codes"])
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_reusable_workflow_cannot_be_waived_with_exact_unknown_pins(self) -> None:
        source = (
            "name: fixture\non: [pull_request, merge_group, push]\n"
            "permissions: {contents: read}\nconcurrency: {group: fixture}\n"
            "jobs:\n  fixture:\n    uses: elsewhere/automation/.github/workflows/fixture.yml@"
            + "a" * 40 + "\n"
        ).encode()
        candidate = reviewed_policy_for(source)
        parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
        self.assertIn("REUSABLE_WORKFLOW_UNSUPPORTED", {item.code for item in parsed["unknowns"]})
        self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_unclassified_and_local_actions_cannot_be_waived_with_exact_pins(self) -> None:
        for action, expected in (
            ("unreviewed/action@" + "a" * 40, "UNCLASSIFIED_EXTERNAL_ACTION"),
            ("./.github/actions/local", "LOCAL_ACTION_UNSUPPORTED"),
        ):
            with self.subTest(action=action):
                source = workflow(extra_step=f"      - uses: {action}\n")
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=reviewed_policy_for(source))
                self.assertIn(expected, {item.code for item in parsed["unknowns"]})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_checkout_repository_override_binds_actual_repository(self) -> None:
        actual_resource = "github:repository:elsewhere/fixture:contents"
        source = workflow().replace(
            f"      - uses: {CHECKOUT_ACTION}\n".encode(),
            (f"      - uses: {CHECKOUT_ACTION}\n" + '        with: {"repos\\u0069tory": elsewhere/fixture}\n').encode(),
        )
        old_policy = reviewed_policy_for(source)
        parsed, _bound = self.assert_source_denied(source, reason="UNDECLARED_EFFECT", candidate=old_policy)
        self.assertEqual({item.resource for item in parsed["effects"]}, {actual_resource})
        corrected = copy.deepcopy(old_policy)
        declaration = corrected["workflow_declarations"][WORKFLOW_PATH]
        declaration["resources"][0]["key"] = actual_resource
        declaration["effects"][0]["resource"] = actual_resource
        _parsed, bound = bind_source(source, candidate=corrected)
        self.assertEqual(bound["verdict"], "ALLOW")
        self.assertEqual(bound["effects"][0]["resource"], actual_resource)
        self.assertTrue(bound["reviewed_unknowns_applied"])

    def test_upload_artifact_binds_literal_and_default_resource_names(self) -> None:
        old_resource = "github:actions:artifact:control-plane-effect"
        for inputs, actual_name in (
            ("", "artifact"),
            ("        with: {name: other-artifact}\n", "other-artifact"),
            ("        with: {NAME: other-artifact}\n", "other-artifact"),
        ):
            with self.subTest(inputs=inputs):
                source = workflow(extra_step=f"      - uses: {UPLOAD_ACTION}\n" + inputs)
                candidate = reviewed_policy_for(source) if inputs else policy_for(source)
                declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
                declaration["resources"].append({"key": old_resource, "access": "external-write"})
                declaration["effects"].append({"sink": "github.artifact.upload", "resource": old_resource, "access": "external-write", "max_calls": 1})
                declaration["max_external_writes"] = 1
                parsed, _bound = self.assert_source_denied(source, reason="UNDECLARED_EFFECT", candidate=candidate)
                actual_resource = "github:actions:artifact:" + actual_name
                self.assertIn(actual_resource, {item.resource for item in parsed["effects"]})
                declaration["resources"][-1]["key"] = actual_resource
                declaration["effects"][-1]["resource"] = actual_resource
                _parsed, corrected = bind_source(source, candidate=candidate)
                self.assertEqual(corrected["verdict"], "ALLOW")

    def test_upload_overwrite_and_dynamic_names_remain_nonwaivable(self) -> None:
        for inputs in (
            "        with: {name: other-artifact, overwrite: true}\n",
            "        with: {NAME: other-artifact, OVERWRITE: true}\n",
            '        with: {name: "${{ github.repository }}"}\n',
            "        with: {name: other-artifact, archive: false}\n",
            "        with: {NAME: other-artifact, ARCHIVE: false}\n",
        ):
            with self.subTest(inputs=inputs):
                source = workflow(extra_step=f"      - uses: {UPLOAD_ACTION}\n" + inputs)
                candidate = reviewed_policy_for(source)
                _parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_action_inputs_with_additional_effects_remain_nonwaivable(self) -> None:
        setup_python = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
        for action, inputs in (
            (CHECKOUT_ACTION, "{submodules: recursive}"),
            (CHECKOUT_ACTION, "{lfs: true}"),
            (CHECKOUT_ACTION, "{allow-unsafe-pr-checkout: true}"),
            (CHECKOUT_ACTION, "{github-server-url: 'https://elsewhere.invalid'}"),
            (CHECKOUT_ACTION, "{path: nested}"),
            (setup_python, "{cache: pip}"),
            (setup_python, "{CACHE: pip}"),
            (setup_python, "{cache-dependency-path: requirements.txt}"),
        ):
            with self.subTest(action=action, inputs=inputs):
                source = workflow(extra_step=f"      - uses: {action}\n        with: {inputs}\n")
                candidate = reviewed_policy_for(source)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertIn("ACTION_EXTRA_EFFECT_UNSUPPORTED", {item.code for item in parsed["unknowns"]})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_checkout_foreign_source_cannot_bind_local_dependency_bytes(self) -> None:
        dependencies = {"scripts/fixture.py": b"pass\n"}
        for inputs in ("{repository: elsewhere/fixture}", "{REPOSITORY: elsewhere/fixture}", "{ref: main}"):
            with self.subTest(inputs=inputs):
                source = workflow(extra_step="      - run: python scripts/fixture.py\n").replace(
                    f"      - uses: {CHECKOUT_ACTION}\n".encode(),
                    f"      - uses: {CHECKOUT_ACTION}\n        with: {inputs}\n".encode(),
                )
                candidate = reviewed_policy_for(source, dependencies=dependencies)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate, dependencies=dependencies)
                self.assertIn("CHECKOUT_SOURCE_BOUNDARY_UNSUPPORTED", {item.code for item in parsed["unknowns"]})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_bounded_artifact_templates_have_distinct_exact_resources(self) -> None:
        for name, expected in (
            ("report-${{ github.run_id }}", "report:run-id"),
            ("report-${{ github.run_id }}-${{ github.run_attempt }}", "report:run-id-run-attempt"),
            ("report-${{ github.sha }}", "report:sha"),
        ):
            with self.subTest(name=name):
                source = workflow(extra_step=f"      - uses: {UPLOAD_ACTION}\n        with:\n          name: {name}\n")
                candidate = reviewed_policy_for(source)
                declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
                resource = "github:actions:artifact-template:" + expected
                declaration["resources"].append({"key": resource, "access": "external-write"})
                declaration["effects"].append({"sink": "github.artifact.upload", "resource": resource, "access": "external-write", "max_calls": 1})
                declaration["max_external_writes"] = 1
                parsed, bound = bind_source(source, candidate=candidate)
                self.assertIn(resource, {effect.resource for effect in parsed["effects"]})
                self.assertEqual(bound["verdict"], "ALLOW")
                # A literal-name contract cannot stand in for the template.
                declaration["resources"][-1]["key"] = "github:actions:artifact:report"
                declaration["effects"][-1]["resource"] = "github:actions:artifact:report"
                self.assert_source_denied(source, reason="UNDECLARED_EFFECT", candidate=candidate)

    def test_hub_manifest_target_is_pinned_as_a_local_dependency(self) -> None:
        manifest = "huggingface/org-card.manifest.json"
        source = workflow(extra_step=f"      - run: echo --manifest {manifest}\n")
        dependencies = {manifest: b'{"target":{"repo_id":"SZLHOLDINGS/README"}}\n'}
        candidate = reviewed_policy_for(source, dependencies=dependencies)
        parsed, bound = bind_source(source, candidate=candidate, dependencies=dependencies)
        self.assertEqual(parsed["dependencies"], [manifest])
        self.assertEqual(bound["verdict"], "ALLOW")
        changed = {manifest: b'{"target":{"repo_id":"elsewhere/other"}}\n'}
        _parsed, bound = self.assert_source_denied(source, reason="REVIEWED_UNKNOWN_PIN_MISMATCH", candidate=candidate, dependencies=changed)
        self.assertFalse(bound["reviewed_unknowns_applied"])
        self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate, dependencies={})
        for value in (f"'{manifest}'", f'"{manifest}"', manifest):
            quoted = workflow(extra_step=f"      - run: echo --manifest {value}\n")
            self.assertEqual(gate.workflow_dependencies(quoted.decode()), [manifest])
        for value in (f'"{manifest} suffix"', f"{manifest}.other", f'"{manifest}', f"'{manifest}\""):
            malformed = workflow(extra_step=f"      - run: echo --manifest {value}\n")
            self.assertNotIn(manifest, gate.workflow_dependencies(malformed.decode()))

    def test_artifact_templates_reject_unbounded_or_destructive_variants(self) -> None:
        for name, extra in (
            ("${{ github.run_id }}", ""),
            ("report-${{ github.event.issue.title }}", ""),
            ("report-${{ github.run_id || inputs.name }}", ""),
            ("report-${{ github.run_id }}-extra", ""),
            ("report-${{ github.run_attempt }}", ""),
            ("../report-${{ github.sha }}", ""),
            ("report-${{ github.run_id }", ""),
            ("report-${{ github.run_id }}", "          overwrite: true\n"),
            ("report-${{ github.sha }}", "          archive: false\n"),
        ):
            with self.subTest(name=name, extra=extra):
                source = workflow(extra_step=f"      - uses: {UPLOAD_ACTION}\n        with:\n          name: {json.dumps(name)}\n{extra}")
                candidate = reviewed_policy_for(source)
                self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)

    def test_event_checkout_refs_require_exact_supported_expression_and_pr_guard(self) -> None:
        dependencies = {"scripts/fixture.py": b"pass\n"}
        for ref, condition, accepted in (
            ("${{ github.sha }}", "github.event_name == 'push'", True),
            ("${{ github.sha }}", None, False),
            ("${{ github.sha }}", "github.event_name != 'workflow_run'", False),
            ("${{ github.event.pull_request.head.sha }}", "github.event_name == 'pull_request'", True),
            ("${{ github.event.pull_request.head.sha }}", None, False),
            ("${{ github.event.pull_request.head.sha }}", "github.event_name != 'push'", False),
            ("${{ github.sha || 'main' }}", None, False),
            ("${{ inputs.sha }}", None, False),
            ("${{ github.event.workflow_run.head_sha }}", None, False),
            ("${{ steps.source.outputs.sha }}", None, False),
        ):
            with self.subTest(ref=ref, condition=condition):
                source = workflow(extra_step="      - run: python scripts/fixture.py\n").replace(
                    f"      - uses: {CHECKOUT_ACTION}\n".encode(),
                    f"      - uses: {CHECKOUT_ACTION}\n        with:\n          ref: {json.dumps(ref)}\n".encode(),
                )
                if condition:
                    source = source.replace(b"    runs-on:", f"    if: {condition}\n    runs-on:".encode())
                candidate = reviewed_policy_for(source, dependencies=dependencies)
                parsed, bound = bind_source(source, candidate=candidate, dependencies=dependencies)
                self.assertEqual("CHECKOUT_SOURCE_BOUNDARY_UNSUPPORTED" not in {u.code for u in parsed["unknowns"]}, accepted)
                self.assertEqual(bound["verdict"], "ALLOW" if accepted else "DENY")

    def guarded_source_fixture(self) -> dict[str, object]:
        # Exercise the independently maintained production resolver, including
        # its env bindings and ordering, rather than importing the analyzer's
        # accepted-script constant as the positive fixture.
        path = CHECKER_PATH.parents[1] / "workflows" / "estate-one-fabric-alignment.yml"
        document, _lines = gate.parse_workflow_yaml(path.read_text(encoding="utf-8"))
        job = document["jobs"]["local-contract"]
        job["steps"] = job["steps"][:3] + [{"run": 'python scripts/fixture.py --sha "${{ steps.source.outputs.sha }}"'}]
        document["jobs"] = {"fixture": job}
        document["on"] = ["pull_request", "push", "workflow_run"]
        return document

    def test_canonical_guarded_checkout_and_hex_run_expression_are_eligible(self) -> None:
        source = json.dumps(self.guarded_source_fixture()).encode()
        parsed = gate.analyze_workflow_source(source.decode(), path=WORKFLOW_PATH)
        self.assertFalse({u.code for u in parsed["unknowns"]} & gate.NON_REVIEWABLE_UNKNOWN_CODES)
        # The eligible boundary still needs exact-source review; it is not an
        # automatically proven shell program.
        self.assertIn("SHELL_COMMAND_UNCLASSIFIED", {u.code for u in parsed["unknowns"]})

    def test_mutated_guarded_checkout_cannot_be_waived(self) -> None:
        mutations = (
            lambda d, s: s[1].update({"if": "always()"}),
            lambda d, s: s[1].update({"continue-on-error": "true"}),
            lambda d, s: s[1].update({"shell": "sh"}),
            lambda d, s: s[1]["env"].update({"FALLBACK_SHA": "${{ inputs.sha }}"}),
            lambda d, s: s[1]["env"].update({"BASH_ENV": "evil.sh"}),
            lambda d, s: d.update({"env": {"BASH_ENV": "evil.sh"}}),
            lambda d, s: s[1].update({"run": s[1]["run"].replace("exit 1", "true")}),
            lambda d, s: s[1].update({"run": s[1]["run"].replace('"$RUN_HEAD_BRANCH" != "main"', '"$RUN_HEAD_BRANCH" = "main"')}),
            lambda d, s: s[1].update({"run": s[1]["run"] + '\necho "sha=main" >> "$GITHUB_OUTPUT"\n'}),
            lambda d, s: s.insert(0, {"run": "echo bad >> $GITHUB_ENV"}),
            lambda d, s: s.append({"id": "source", "run": "true"}),
            lambda d, s: s.insert(1, s.pop(2)),  # output consumed before resolver
            lambda d, s: s[2]["with"].update({"repository": "elsewhere/fixture"}),
            lambda d, s: s[2].update({"if": "always()"}),
            lambda d, s: s[-1].update({"if": "always()"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                document = self.guarded_source_fixture()
                mutate(document, document["jobs"]["fixture"]["steps"])
                source = json.dumps(document).encode()
                dependencies = {"scripts/fixture.py": b"pass\n"}
                candidate = reviewed_policy_for(source, dependencies=dependencies)
                parsed, _bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate, dependencies=dependencies)
                self.assertTrue({"CHECKOUT_SOURCE_BOUNDARY_UNSUPPORTED", "WORKFLOW_EXPRESSION_EXECUTION_UNSUPPORTED"} & {u.code for u in parsed["unknowns"]})

    def test_shell_interpolation_only_accepts_provider_hex_or_numeric_values(self) -> None:
        for value, accepted in (
            ("github.sha", True), ("github.run_id", True), ("github.run_attempt", True),
            ("github.event.issue.title", False), ("github.ref", False),
            ("steps.source.outputs.sha", False), ("github.sha || inputs.fallback", False),
            ("format('{0}', github.sha)", False),
        ):
            with self.subTest(value=value):
                source = workflow(extra_step='      - run: echo "${{ ' + value + ' }}"\n')
                parsed = gate.analyze_workflow_source(source.decode(), path=WORKFLOW_PATH)
                self.assertEqual("WORKFLOW_EXPRESSION_EXECUTION_UNSUPPORTED" not in {u.code for u in parsed["unknowns"]}, accepted)

    def test_action_input_case_collisions_are_nonwaivable(self) -> None:
        source = workflow(extra_step=f"      - uses: {UPLOAD_ACTION}\n        with: {{name: fixture, NAME: other-artifact}}\n")
        candidate = reviewed_policy_for(source)
        parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
        self.assertIn("WORKFLOW_SHAPE_INVALID", {item.code for item in parsed["unknowns"]})
        self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_unicode_action_input_names_cannot_alias_ascii_runtime_inputs(self) -> None:
        for spelling in ("\u017fubmodules", '"\\u017fubmodules"'):
            with self.subTest(spelling=spelling):
                source = workflow().replace(
                    f"      - uses: {CHECKOUT_ACTION}\n".encode(),
                    f"      - uses: {CHECKOUT_ACTION}\n        with: {{{spelling}: true}}\n".encode(),
                )
                candidate = reviewed_policy_for(source)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertIn("WORKFLOW_SHAPE_INVALID", {item.code for item in parsed["unknowns"]})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_action_auth_inputs_with_unresolved_sources_are_nonwaivable(self) -> None:
        setup_python = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
        for action in (CHECKOUT_ACTION, setup_python):
            for input_name in ("token", "ssh-key"):
                for value, names in (
                    ("${{ vars.FIXTURE_AUTH }}", []),
                    ("${{ inputs.fixture_auth }}", []),
                    ("${{ env.FIXTURE_AUTH }}", []),
                    ("fixture-value", []),
                    ("${{ secrets.FIXTURE_AUTH || inputs.fallback }}", ["FIXTURE_AUTH"]),
                ):
                    with self.subTest(action=action, input_name=input_name, value=value):
                        step = f"      - uses: {action}\n        with: {{{input_name}: {json.dumps(value)}}}\n"
                        source = workflow().replace(f"      - uses: {CHECKOUT_ACTION}\n".encode(), step.encode()) if action == CHECKOUT_ACTION else workflow(extra_step=step)
                        candidate = reviewed_policy_for(source, credentials=names)
                        parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                        self.assertEqual(parsed["credentials"], names)
                        self.assertFalse(parsed["controls"]["no_explicit_secrets"])
                        self.assertIn("SECRET_NAME_UNRESOLVED", {item.code for item in parsed["unknowns"]})
                        self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_action_auth_inputs_with_declared_names_keep_exact_review_path(self) -> None:
        setup_python = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
        for action in (CHECKOUT_ACTION, setup_python):
            for input_name in ("TOKEN", "SSH-KEY"):
                for value, names in (
                    ("${{ secrets.FIXTURE_AUTH }}", ["FIXTURE_AUTH"]),
                    ("${{ secrets['FIXTURE_AUTH'] }}", ["FIXTURE_AUTH"]),
                    ("${{ github.token }}", ["GITHUB_TOKEN"]),
                    ("${{ github['token'] || secrets.FIXTURE_AUTH }}", ["FIXTURE_AUTH", "GITHUB_TOKEN"]),
                ):
                    with self.subTest(action=action, input_name=input_name, value=value):
                        step = f"      - uses: {action}\n        with: {{{input_name}: {json.dumps(value)}}}\n"
                        source = workflow().replace(f"      - uses: {CHECKOUT_ACTION}\n".encode(), step.encode()) if action == CHECKOUT_ACTION else workflow(extra_step=step)
                        candidate = reviewed_policy_for(source, credentials=names)
                        if action == setup_python:
                            declaration = candidate["workflow_declarations"][WORKFLOW_PATH]
                            declaration["resources"].append({"key": "runner:toolchain:python", "access": "local-write"})
                            declaration["effects"].append({"sink": "runner.toolchain.install", "resource": "runner:toolchain:python", "access": "local-write", "max_calls": 1})
                        parsed, bound = bind_source(source, candidate=candidate)
                        self.assertEqual(parsed["credentials"], names)
                        self.assertFalse(parsed["controls"]["no_explicit_secrets"])
                        self.assertNotIn("SECRET_NAME_UNRESOLVED", {item.code for item in parsed["unknowns"]})
                        self.assertEqual(bound["verdict"], "ALLOW")
                        self.assertTrue(bound["reviewed_unknowns_applied"])

    def test_dynamic_checkout_repository_cannot_be_reviewed_into_authority(self) -> None:
        expression = "$" + "{{ github.repository }}"
        source = workflow().replace(
            f"      - uses: {CHECKOUT_ACTION}\n".encode(),
            (f"      - uses: {CHECKOUT_ACTION}\n" + f'        with: {{repository: "{expression}"}}\n').encode(),
        )
        candidate = reviewed_policy_for(source)
        parsed, _bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
        self.assertIn("ACTION_RESOURCE_OVERRIDE_UNSUPPORTED", {item.code for item in parsed["unknowns"]})
        self.assertEqual(parsed["effects"], [])

    def test_ambiguous_yaml_is_nonwaivable_even_with_matching_source_and_pins(self) -> None:
        baseline = workflow().decode("utf-8")
        candidates = (
            (baseline.replace("permissions:\n", "permissions: {contents: read}\npermissions:\n"), "YAML_DUPLICATE_KEY"),
            (baseline + "      - run: true\n        run: true\n", "YAML_DUPLICATE_KEY"),
            (baseline + '      - {run: true, "r\\u0075n": true}\n', "YAML_DUPLICATE_KEY"),
            (baseline + "---\nname: second\n", "YAML_INVALID"),
            (baseline.replace("name: fixture", "name: !!str fixture"), "YAML_INDIRECTION_UNSUPPORTED"),
            (baseline.replace("name: fixture", "name: &display fixture"), "YAML_INDIRECTION_UNSUPPORTED"),
            (baseline.replace("name: fixture", "name: *display"), "YAML_INDIRECTION_UNSUPPORTED"),
            (baseline.replace("concurrency:\n", "concurrency:\n  <<: {group: fixture}\n"), "YAML_INDIRECTION_UNSUPPORTED"),
            ("%YAML 1.2\n---\n" + baseline, "YAML_DIRECTIVE_UNSUPPORTED"),
        )
        for spelling, expected in candidates:
            with self.subTest(expected=expected, spelling=spelling):
                source = spelling.encode()
                candidate = reviewed_policy_for(source)
                parsed, _bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertIn(expected, {item.code for item in parsed["unknowns"]})

    def test_unknown_root_and_job_keys_cannot_extend_execution_model(self) -> None:
        for source in (
            workflow() + b"unsupported-execution: true\n",
            workflow().replace(b"    steps:\n", b"    Container: example.invalid/fixture:latest\n    steps:\n"),
            workflow().replace(b"    steps:\n", b"    unsupported-execution: true\n    steps:\n"),
        ):
            with self.subTest(source=source):
                candidate = reviewed_policy_for(source)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertIn("WORKFLOW_SHAPE_INVALID", {item.code for item in parsed["unknowns"]})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_workflow_parser_size_depth_and_event_limits_are_nonwaivable(self) -> None:
        for boundary, spelling in (
            ("size", "name: " + "x" * 1_048_577 + "\n"),
            ("depth", "name: " + "[" * 65 + "x" + "]" * 65 + "\n"),
            ("events", "name: [" + ",".join("x" for _index in range(20_000)) + "]\n"),
        ):
            with self.subTest(boundary=boundary):
                source = spelling.encode()
                candidate = reviewed_policy_for(source)
                parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertEqual({item.code for item in parsed["unknowns"]}, {"YAML_LIMIT_EXCEEDED"})
                self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_parser_unavailability_and_wrong_version_are_nonwaivable(self) -> None:
        source = workflow()
        yaml_module = importlib.import_module("yaml")
        for context in (
            mock.patch.dict(sys.modules, {"yaml": None}),
            mock.patch.object(yaml_module, "__version__", "6.0.2"),
        ):
            with self.subTest(context=type(context).__name__), context:
                candidate = reviewed_policy_for(source)
                parsed, _bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
                self.assertEqual({item.code for item in parsed["unknowns"]}, {"YAML_PARSER_UNAVAILABLE"})

    def test_decoded_local_dependency_paths_are_included_in_binding(self) -> None:
        source = workflow(extra_step='      - "r\\u0075n": "python scripts/fi\\u0078ture.py"\n')
        parsed, _bound = self.assert_source_denied(source, reason="UNKNOWN_EFFECT")
        self.assertEqual(parsed["dependencies"], ["scripts/fixture.py"])
        dependencies = {"scripts/fixture.py": b"pass\n"}
        candidate = reviewed_policy_for(source, dependencies=dependencies)
        _parsed, bound = bind_source(source, candidate=candidate, dependencies=dependencies)
        self.assertEqual(bound["verdict"], "ALLOW")
        self.assertEqual(bound["dependencies"], [{"path": "scripts/fixture.py", "sha256": gate.sha256_bytes(b"pass\n")}])
        local_uses = workflow(extra_step='      - "u\\u0073es": "./.github/workflows/fi\\u0078ture.yml"\n')
        self.assertEqual(gate.workflow_dependencies(local_uses.decode()), [".github/workflows/fixture.yml"])

    def test_missing_dependency_cannot_be_waived_by_unknown_entry(self) -> None:
        source = workflow(extra_step="      - run: python scripts/fixture.py\n")
        candidate = reviewed_policy_for(source)
        candidate["workflow_declarations"][WORKFLOW_PATH]["reviewed_unknowns"]["unknowns"].append(
            f"LOCAL_DEPENDENCY_MISSING@{WORKFLOW_PATH}:1"
        )
        _parsed, bound = self.assert_source_denied(source, reason="UNREVIEWABLE_EFFECT_BOUNDARY", candidate=candidate)
        self.assertIn("LOCAL_DEPENDENCY_MISSING", {item["code"] for item in bound["unknowns"]})
        self.assertFalse(bound["reviewed_unknowns_applied"])

    def test_metadata_cannot_supply_required_execution_control_hints(self) -> None:
        source = workflow(name="refs/heads/main GITHUB_REF git rev-parse HEAD_SHA expected-before readback")
        candidate = policy_for(source)
        controls = candidate["workflow_declarations"][WORKFLOW_PATH]["required_controls"]
        for name in ("protected_ref", "exact_sha", "expected_before", "readback"):
            controls[name] = True
        parsed, bound = self.assert_source_denied(source, reason="CONTROL_EXACT_SHA_MISSING", candidate=candidate)
        for name in ("protected_ref", "exact_sha", "expected_before", "readback"):
            self.assertFalse(parsed["controls"][name])
            self.assertIn(f"CONTROL_{name.upper()}_MISSING", bound["reason_codes"])

    def test_exact_reviewed_shell_unknowns_still_allow(self) -> None:
        source = workflow(extra_step="      - run: opaque-tool fixture\n")
        candidate = reviewed_policy_for(source)
        parsed, bound = bind_source(source, candidate=candidate)
        self.assertEqual({item.code for item in parsed["unknowns"]}, {"SHELL_COMMAND_UNCLASSIFIED"})
        self.assertEqual(bound["verdict"], "ALLOW")
        self.assertEqual(bound["reason_codes"], [])
        self.assertTrue(bound["reviewed_unknowns_applied"])

    def test_reviewed_unknown_pin_and_set_drift_still_deny(self) -> None:
        source = workflow(extra_step="      - run: opaque-tool fixture\n")
        for mismatch in ("pin", "set"):
            with self.subTest(mismatch=mismatch):
                candidate = reviewed_policy_for(source)
                reviewed = candidate["workflow_declarations"][WORKFLOW_PATH]["reviewed_unknowns"]
                if mismatch == "pin":
                    reviewed["files"][WORKFLOW_PATH] = gate.sha256_bytes(workflow())
                    expected = "REVIEWED_UNKNOWN_PIN_MISMATCH"
                else:
                    reviewed["unknowns"].append(f"DYNAMIC_EXECUTION@{WORKFLOW_PATH}:1")
                    expected = "REVIEWED_UNKNOWN_SET_MISMATCH"
                _parsed, bound = self.assert_source_denied(source, reason=expected, candidate=candidate)
                self.assertFalse(bound["reviewed_unknowns_applied"])


class GitReceiptTests(unittest.TestCase):
    def test_no_effect_change_is_deterministic_and_has_object_provenance(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.write(WORKFLOW_PATH, workflow(name="fixture renamed display"))
            changed_source = workflow(name="fixture renamed display")
            fixture.write(
                POLICY_PATH, policy_bytes(policy_for(changed_source))
            )
            head = fixture.commit("change display name and bind new source")
            first = analyze(fixture.root, base, head)
            second = analyze(fixture.root, base, head)
            self.assertEqual(gate.canonical_bytes(first), gate.canonical_bytes(second))
            self.assertEqual(first["base_revision"], base)
            self.assertEqual(first["head_revision"], head)
            self.assertEqual(first["merge_base"], base)
            self.assertRegex(first["base_tree"], r"^[0-9a-f]{40}$")
            self.assertRegex(first["head_tree"], r"^[0-9a-f]{40}$")
            self.assertRegex(first["diff_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(first["decision_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertFalse(first["provider_calls_performed"])
            self.assertFalse(first["secret_values_recorded"])

    def test_trust_root_change_requires_independent_review(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.write(CHECKER_REPO_PATH, b"# fixture checker change\n")
            head = fixture.commit("change analyzer")
            receipt = analyze(fixture.root, base, head)
            self.assertEqual(receipt["verdict"], "REVIEW_REQUIRED")
            self.assertIn(
                "TRUST_ROOT_CHANGED_REVIEW_REQUIRED", receipt["reason_codes"]
            )
            self.assertNotEqual(
                receipt["claim"], "VERIFIED_STATIC_EFFECT_BOUNDARY"
            )

    def test_trust_root_bundled_with_matching_digest_denied_workflow_stays_deny(self) -> None:
        source = workflow(extra_step='      - {"r\\u0075n": "git push origin main"}\n')
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.write(CHECKER_REPO_PATH, b"# fixture checker change\n")
            fixture.write(WORKFLOW_PATH, source)
            fixture.write(POLICY_PATH, policy_bytes(policy_for(source)))
            head = fixture.commit("bundle analyzer change with undeclared workflow write")
            receipt = analyze(fixture.root, base, head)
            self.assertEqual(receipt["verdict"], "DENY")
            self.assertIn("TRUST_ROOT_BUNDLED_WITH_DENIED_WORKFLOW", receipt["reason_codes"])
            self.assertIn("UNDECLARED_EFFECT", receipt["reason_codes"])
            self.assertNotIn("WORKFLOW_DIGEST_MISMATCH", receipt["reason_codes"])
            self.assertNotEqual(receipt["claim"], "VERIFIED_STATIC_EFFECT_BOUNDARY")

    def test_decoded_dependency_change_selects_unchanged_workflow(self) -> None:
        source = workflow(extra_step='      - run: "python scripts/fi\\u0078ture.py"\n')
        dependencies = {"scripts/fixture.py": b"pass\n"}
        with TemporaryRepository() as fixture:
            fixture.write(WORKFLOW_PATH, source)
            fixture.write("scripts/fixture.py", dependencies["scripts/fixture.py"])
            fixture.write(POLICY_PATH, policy_bytes(reviewed_policy_for(source, dependencies=dependencies)))
            base = fixture.commit("baseline with encoded workflow dependency")
            fixture.write("scripts/fixture.py", b"import requests\nrequests.post('https://example.invalid/api')\n")
            head = fixture.commit("mutate decoded local dependency")
            receipt = analyze(fixture.root, base, head)
            self.assertEqual(receipt["verdict"], "DENY")
            self.assertNotIn(WORKFLOW_PATH, receipt["changed_paths"])
            self.assertNotIn("WORKFLOW_DIGEST_MISMATCH", receipt["reason_codes"])
            self.assertIn("REVIEWED_UNKNOWN_PIN_MISMATCH", receipt["reason_codes"])
            self.assertEqual([item["workflow"] for item in receipt["analyses"]], [WORKFLOW_PATH])
            self.assertIn("UNDECLARED_EFFECT", receipt["analyses"][0]["reason_codes"])

    def test_workflow_deletion_is_recorded_and_denied(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.root.joinpath(*WORKFLOW_PATH.split("/")).unlink()
            head = fixture.commit("delete workflow")
            receipt = analyze(fixture.root, base, head)
            self.assertEqual(receipt["verdict"], "DENY")
            self.assertIn("WORKFLOW_DELETION_DENIED", receipt["reason_codes"])
            changed = [
                item for item in receipt["changed_objects"] if item["path"] == WORKFLOW_PATH
            ]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0]["status"], "D")
            self.assertRegex(changed[0]["old_blob"], r"^[0-9a-f]{40}$")
            self.assertIsNone(changed[0]["new_blob"])

    def test_mode_only_change_is_visible_in_receipt(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.git("update-index", "--chmod=+x", WORKFLOW_PATH)
            fixture.git("commit", "-q", "-m", "change workflow mode")
            head = fixture.git("rev-parse", "HEAD")
            receipt = analyze(fixture.root, base, head)
            changed = [
                item for item in receipt["changed_objects"] if item["path"] == WORKFLOW_PATH
            ]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0]["old_mode"], "100644")
            self.assertEqual(changed[0]["new_mode"], "100755")
            self.assertEqual(changed[0]["old_blob"], changed[0]["new_blob"])

    def test_symlink_git_mode_is_rejected_before_analyzing_source(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            blob = fixture.git("rev-parse", f"HEAD:{WORKFLOW_PATH}")
            fixture.git(
                "update-index",
                "--cacheinfo",
                f"120000,{blob},{WORKFLOW_PATH}",
            )
            fixture.git("commit", "-q", "-m", "stage symlink mode")
            head = fixture.git("rev-parse", "HEAD")
            with self.assertRaises(gate.GateError) as raised:
                analyze(fixture.root, base, head)
            self.assertEqual(raised.exception.code, "UNSUPPORTED_GIT_MODE")

    def test_casefold_collision_in_head_git_tree_is_rejected(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            blob = fixture.git("rev-parse", f"HEAD:{WORKFLOW_PATH}")
            fixture.git(
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob},.github/workflows/Fixture.yml",
            )
            fixture.git("commit", "-q", "-m", "stage case collision")
            head = fixture.git("rev-parse", "HEAD")
            with self.assertRaises(gate.GateError) as raised:
                analyze(fixture.root, base, head)
            self.assertEqual(raised.exception.code, "PATH_COLLISION")

    def test_rename_records_old_and_new_paths(self) -> None:
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            renamed = ".github/workflows/renamed.yml"
            fixture.git("mv", WORKFLOW_PATH, renamed)
            head_policy = policy_for(workflow(), workflow_path=renamed)
            fixture.write(POLICY_PATH, policy_bytes(head_policy))
            head = fixture.commit("rename workflow and declaration")
            receipt = analyze(fixture.root, base, head)
            serialized = gate.canonical_bytes(receipt)
            self.assertIn(WORKFLOW_PATH.encode("utf-8"), serialized)
            self.assertIn(renamed.encode("utf-8"), serialized)
            old = next(
                item for item in receipt["changed_objects"]
                if item["path"] == WORKFLOW_PATH
            )
            new = next(
                item for item in receipt["changed_objects"]
                if item["path"] == renamed
            )
            self.assertEqual((old["status"], new["status"]), ("D", "A"))
            self.assertEqual(old["old_blob"], new["new_blob"])

    def test_receipt_never_contains_secret_value_or_source_snippet(self) -> None:
        fixture_marker = "CANARY-NEVER-IN-RECEIPT-7f4c6329"
        secret_expression = "$" + "{{ secrets.HF_TOKEN }}"
        source = workflow(
            extra_step=(
                "      - env:\n"
                f"          HF_TOKEN: {secret_expression}\n"
                f"      - run: echo {fixture_marker}\n"
            )
        )
        with TemporaryRepository() as fixture:
            base = fixture.install_baseline()
            fixture.write(WORKFLOW_PATH, source)
            fixture.write(
                POLICY_PATH,
                policy_bytes(policy_for(source, credentials=["HF_TOKEN"])),
            )
            head = fixture.commit("add credential reference")
            receipt = analyze(fixture.root, base, head)
            encoded = gate.canonical_bytes(receipt)
            self.assertNotIn(fixture_marker.encode("utf-8"), encoded)
            self.assertNotIn(secret_expression.encode("utf-8"), encoded)
            self.assertIn(b"HF_TOKEN", encoded)
            self.assertFalse(receipt["secret_values_recorded"])

    def test_invalid_revision_fails_with_sanitized_receipt(self) -> None:
        marker = "CANARY-ERROR-TEXT-NEVER-SERIALIZE"
        failure = gate.failure_receipt(
            "a" * 40, "b" * 40, gate.GateError("REVISION_INVALID", marker)
        )
        self.assertEqual(failure["verdict"], "DENY")
        self.assertEqual(failure["reason_codes"], ["REVISION_INVALID"])
        self.assertNotIn(marker.encode("utf-8"), gate.canonical_bytes(failure))


if __name__ == "__main__":
    unittest.main(verbosity=2)
