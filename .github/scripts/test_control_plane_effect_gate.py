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
