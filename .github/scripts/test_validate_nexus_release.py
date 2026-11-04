#!/usr/bin/env python3
# Copyright 2026 SZL Holdings - SPDX-License-Identifier: Apache-2.0
"""Offline request, actual-workflow graph and shell-wiring release contracts."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SPEC = importlib.util.spec_from_file_location("validate_nexus_release", HERE / "validate_nexus_release.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Nexus release validator")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
A, B, POLICY = "a" * 40, "b" * 40, "c" * 40


def context() -> dict[str, str]:
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "szl-holdings/.github",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": release.WORKFLOW_REF,
        "GITHUB_SHA": POLICY,
        "GITHUB_WORKFLOW_SHA": POLICY,
    }


def workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/publish-nexus-space.yml").read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def job_allowed(expression: str, values: dict) -> bool:
    """Evaluate this policy's small AND/equality grammar, never arbitrary eval."""
    result = True
    for term in expression.split(" && "):
        if term == "github.ref_protected":
            result = result and values["ref_protected"] is True
        else:
            match = re.fullmatch(r"github\.(event_name|repository|ref) == '([^']*)'", term)
            require(match is not None, "unexpected job condition grammar")
            result = result and values[match[1]] == match[2]
    return result


def commands(step: dict, script: str) -> list[list[str]]:
    """Inspect executable shell command lines, not workflow comments or echoes."""
    found = []
    for line in step.get("run", "").replace("\\\n", " ").splitlines():
        if script not in line or line.lstrip().startswith(("#", "echo ", "printf ")):
            continue
        tokens = shlex.split(line, comments=True)
        for index, token in enumerate(tokens):
            if token.endswith("/" + script):
                found.append(tokens[index + 1:])
    return found


def check_workflow(doc: dict) -> None:
    """Check the actual workflow graph, gate, command arguments and ordering."""
    events = doc.get("on", doc.get(True))
    require(set(events) == {"workflow_dispatch"}, "only explicit dispatch may publish")
    source = events["workflow_dispatch"]["inputs"]["source_sha"]
    require(source.get("required") is True and source.get("type") == "string"
            and "default" not in source, "exact source input must be explicit")
    require(set(doc["jobs"]) == {"validate", "publish"}, "unexpected release job")
    require("concurrency" not in doc, "read-only validation must not share a deployment lock")
    validate, publish = doc["jobs"]["validate"], doc["jobs"]["publish"]
    admitted = dict(event_name="workflow_dispatch", repository="szl-holdings/.github",
                    ref="refs/heads/main", ref_protected=True)
    for job in (validate, publish):
        require(job_allowed(job["if"], admitted), "owner main dispatch must be admitted")
        for key, bad in (("event_name", "push"), ("event_name", "schedule"),
                         ("event_name", "pull_request"), ("repository", "fork/.github"),
                         ("ref", "refs/heads/feature"), ("ref_protected", False)):
            require(not job_allowed(job["if"], {**admitted, key: bad}), "job boundary bypass")
        require(job.get("permissions") == {"contents": "read"}, "release token must be read-only")
        for step in job["steps"]:
            if "uses" in step:
                require(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", step["uses"]) is not None,
                        "actions must remain immutable")
                if step["uses"].startswith("actions/checkout@"):
                    require(step["with"].get("ref")
                            == "${{ github.event.pull_request.head.sha || github.event.merge_group.head_sha || github.sha }}"
                            and step["with"].get("persist-credentials") is False,
                            "checkout must use the exact policy without persisted credentials")
    require("environment" not in validate and "secrets." not in json.dumps(validate),
            "validation must not acquire provider credentials")
    for step in validate["steps"]:
        run = step.get("run", "")
        require(not commands(step, "hf_deploy_from_dockerfile.py")
                and not commands(step, "acquire_hf_publisher_token.py")
                and not re.search(r"\b(?:curl|wget)\b", run),
                "no provider mutation/acquisition before environment approval")
    require(publish.get("environment") == "production", "fixed existing environment required")
    require(publish.get("needs") == "validate", "successful read-only admission required")
    require(publish.get("concurrency") == {"group": "publish-nexus-space",
                                          "cancel-in-progress": False},
            "deployment concurrency must be fixed and non-cancelling")
    require(validate["outputs"]["source_sha"] == "${{ steps.source_ref.outputs.sha }}",
            "source output must come from checked-out validated revision")
    require(any(commands(s, "validate_nexus_source_binding.py") for s in validate["steps"]),
            "source binding must be validated before approval")
    require(publish["env"]["REQUESTED_SOURCE_SHA"] == "${{ needs.validate.outputs.source_sha }}"
            and "${{ needs.validate.outputs.source_sha }}" in publish["name"],
            "reviewer must see and publisher must consume the sealed requested revision")
    by_id = {s["id"]: s for s in publish["steps"] if "id" in s}
    positions = {s["id"]: i for i, s in enumerate(publish["steps"]) if "id" in s}
    ordered = ["source_ref", "source", "freshness", "credential", "deploy", "restart", "attest", "cleanup"]
    require(all(key in by_id for key in ordered), "required publication stages absent")
    require([positions[k] for k in ordered] == sorted(positions[k] for k in ordered),
            "freshness, credential, mutation and cleanup order changed")
    for key in ordered[:-1]:
        require("if" not in by_id[key] and not by_id[key].get("continue-on-error"),
                "required release guard may not be skipped or ignored")
    require(by_id["cleanup"].get("if") == "always()", "credential cleanup must always run")
    for step in (by_id["source_ref"], by_id["freshness"]):
        invocations = commands(step, "validate_nexus_release.py")
        require(any('--main-sha=$REMOTE_SHA' in c and
                    any(a.startswith("--checkout-sha=") for a in c) for c in invocations),
                "current main and checkout must be checked against approval")
    require(by_id["source"]["env"]["RESOLVED_SOURCE_SHA"] == "${{ steps.source_ref.outputs.sha }}",
            "publication source must remain bound to the approved checkout")
    binding = commands(by_id["source"], "validate_nexus_source_binding.py")
    require(len(binding) == 1 and "source/space/Dockerfile" in binding[0]
            and "--report" in binding[0], "publication source-binding evidence required")
    require(by_id["deploy"]["env"]["SOURCE_SHA"] == "${{ steps.source.outputs.sha }}",
            "deployment must use the validated source")
    deploy = commands(by_id["deploy"], "hf_deploy_from_dockerfile.py")
    require(len(deploy) == 1, "one content publication command required")
    for flag in ("--require-default-branch-tip", "--prune", "--ref", "--source-sha",
                 "--dockerfile-path", "--manifest-out", "--smoke-paths"):
        require(flag in deploy[0], f"retained deploy guard absent: {flag}")
    for flag in ("--ref", "--source-sha"):
        require(deploy[0][deploy[0].index(flag) + 1] == "$SOURCE_SHA",
                "deployer revision may not float")
    require(deploy[0][deploy[0].index("--dockerfile-path") + 1] == "space/Dockerfile",
            "Docker source closure changed")
    acquire = commands(by_id["credential"], "acquire_hf_publisher_token.py")
    require(len(acquire) == 1 and "--target-type" in acquire[0]
            and acquire[0][acquire[0].index("--target-type") + 1] == "space"
            and "--token-file" in acquire[0], "independent credential validation required")
    for alias in ("HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_WRITE_TOKEN", "HF_TOKEN"):
        require(by_id["credential"]["env"].get(alias + "_CANDIDATE")
                == "${{ secrets." + alias + " }}", "independent candidate credential lost")
    for key in ("credential", "deploy", "restart", "attest"):
        require(by_id[key]["env"].get("HF_REPO") == "SZLHOLDINGS/nexus",
                "publication target must remain exact")
    require("600" in shlex.split(by_id["deploy"]["run"]),
            "content publication must retain mode-0600 token handling")
    for key, flag in (("restart", "--restart-space"), ("attest", "--attest")):
        call = commands(by_id[key], "hf_deploy_from_dockerfile.py")
        require(len(call) == 1 and flag in call[0] and "--manifest" in call[0],
                "manifest-bound runtime/byte checks required")
        require("600" in shlex.split(by_id[key]["run"]), "mode-0600 token handling required")
    attest = commands(by_id["attest"], "hf_deploy_from_dockerfile.py")[0]
    require("--wait-running" in attest and attest[attest.index("--wait-running") + 1] == "1200",
            "running attestation bound must remain")
    require("rm" in shlex.split(by_id["cleanup"]["run"]), "ephemeral credential must be removed")
    installs = [i for i, s in enumerate(publish["steps"])
                if "--require-hashes" in shlex.split(s.get("run", "").replace("\\\n", " "))]
    require(installs and max(installs) < positions["credential"], "hash lock must precede credentials")
    for i in installs:
        tokens = shlex.split(publish["steps"][i]["run"].replace("\\\n", " "))
        require("--only-binary=:all:" in tokens and "--ignore-installed" in tokens
                and "requirements/hf-publisher.lock" in tokens, "locked dependency closure changed")


class ReleaseRequestTests(unittest.TestCase):
    def test_exact_context_and_current_source_are_admitted(self):
        self.assertEqual(A, release.validate_request(context(), A, POLICY))
        release.validate_source(A, A, A)

    def test_absent_invalid_floating_and_injected_revisions_are_denied(self):
        for bad in ("", "main", "HEAD", "refs/heads/main", "a" * 39, "a" * 41,
                    "A" * 40, A + "\n", " " + A, A + " ", "g" * 40,
                    "$(touch SHOULD_NOT_EXIST)", A + "; exit 0", "--help", None, 123):
            with self.subTest(value=bad), self.assertRaises(release.ReleaseError):
                release.validate_request(context(), bad, POLICY)

    def test_every_required_context_field_is_fail_closed(self):
        for key in context():
            for bad in ("", "wrong"):
                with self.subTest(key=key, value=bad), self.assertRaises(release.ReleaseError):
                    release.validate_request({**context(), key: bad}, A, POLICY)

    def test_policy_checkout_must_equal_workflow_and_event(self):
        with self.assertRaises(release.ReleaseError):
            release.validate_request(context(), A, B)
        with self.assertRaises(release.ReleaseError):
            release.validate_request({**context(), "GITHUB_WORKFLOW_SHA": B}, A, POLICY)

    def test_stale_or_substituted_checkout_never_upgrades_or_rolls_back(self):
        for checkout, main in ((A, B), (B, A), (B, B), ("main", A), (A, "")):
            with self.subTest(checkout=checkout, main=main), self.assertRaises(release.ReleaseError):
                release.validate_source(A, checkout, main)

    def test_cli_must_not_accept_half_a_tip_check(self):
        with patch.dict(os.environ, context(), clear=True):
            for incomplete in (["--main-sha", A], ["--checkout-sha", A]):
                self.assertEqual(1, release.main(["--source-sha", A, "--policy-sha", POLICY, *incomplete]))


class WorkflowTests(unittest.TestCase):
    def test_actual_workflow_graph_and_retained_guards(self):
        check_workflow(workflow())

    def test_gate_and_order_mutations_are_rejected(self):
        mutations = {
            "automatic schedule": lambda w: w["on"].update(schedule=[]),
            "automatic push": lambda w: w["on"].update(push={}),
            "optional input": lambda w: w["on"]["workflow_dispatch"]["inputs"]["source_sha"].update(required=False),
            "default floating input": lambda w: w["on"]["workflow_dispatch"]["inputs"]["source_sha"].update(default="main"),
            "missing environment": lambda w: w["jobs"]["publish"].pop("environment"),
            "dynamic environment": lambda w: w["jobs"]["publish"].update(environment="${{ inputs.environment }}"),
            "missing dependency": lambda w: w["jobs"]["publish"].pop("needs"),
            "other event": lambda w: w["jobs"]["publish"].update(**{"if": "github.event_name == 'push'"}),
            "unprotected ref": lambda w: w["jobs"]["publish"].update(**{"if": "github.event_name == 'workflow_dispatch'"}),
            "cancelling deployment": lambda w: w["jobs"]["publish"]["concurrency"].update(**{"cancel-in-progress": True}),
            "event-dependent concurrency": lambda w: w["jobs"]["publish"]["concurrency"].update(group="publish-${{ github.event_name }}"),
            "credential before approval": lambda w: w["jobs"]["validate"]["steps"].append({"run": "python .github/scripts/acquire_hf_publisher_token.py --target-type space"}),
            "mutation before approval": lambda w: w["jobs"]["validate"]["steps"].append({"run": "python .github/scripts/hf_deploy_from_dockerfile.py --restart-space"}),
            "freshness ignored": lambda w: next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "freshness").update(**{"continue-on-error": True}),
            "credential reordered": lambda w: w["jobs"]["publish"]["steps"].reverse(),
            "tip guard removed": lambda w: next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "deploy").update(run=next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "deploy")["run"].replace("--require-default-branch-tip", "")),
            "attestation removed": lambda w: next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "attest").update(run=next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "attest")["run"].replace("--attest", "")),
            "token mode guard removed": lambda w: next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "deploy").update(run=next(s for s in w["jobs"]["publish"]["steps"] if s.get("id") == "deploy")["run"].replace('"600"', '"644"')),
            "preapproval binding removed": lambda w: next(s for s in w["jobs"]["validate"]["steps"] if s.get("id") == "source_ref").update(run=next(s for s in w["jobs"]["validate"]["steps"] if s.get("id") == "source_ref")["run"].replace("validate_nexus_source_binding.py", "unreviewed.py")),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                changed = copy.deepcopy(workflow())
                mutate(changed)
                with self.assertRaises(ValueError):
                    check_workflow(changed)

    def test_general_ci_runs_contract_when_publisher_disabled(self):
        ci = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
        events = ci.get("on", ci.get(True))
        self.assertIn("pull_request", events)
        self.assertIn("main", events["push"]["branches"])
        self.assertIn("merge_group", events)
        job = ci["jobs"]["test"]
        self.assertNotIn("if", job)
        self.assertNotIn("environment", job)
        self.assertNotIn("secrets.", json.dumps(job))
        self.assertTrue(any(commands(step, "test_validate_nexus_release.py") for step in job["steps"]))


class ActualShellWiringTests(unittest.TestCase):
    """Execute the real critical steps, substituting ONLY the Git transport."""

    def run_step(self, step, requested=A, main=A, checkout=A, event=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / ".github/scripts"
            scripts.mkdir(parents=True)
            for name in ("validate_nexus_release.py", "validate_nexus_source_binding.py"):
                (scripts / name).write_bytes((HERE / name).read_bytes())
            (root / "source/space").mkdir(parents=True)
            (root / "source/space/Dockerfile").write_text("COPY SOURCE_GITHUB_SHA /app/SOURCE_GITHUB_SHA\n")
            # Source-fetch steps require absence before init; freshness needs a checkout.
            if step.get("id") == "source_ref":
                (root / "source/space/Dockerfile").unlink()
                (root / "source/space").rmdir()
                (root / "source").rmdir()
            binary = root / "bin"
            binary.mkdir()
            fake = binary / "git"
            fake.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ["GIT_CALLS"], "a") as out:
    out.write(json.dumps(args) + "\\n")
if args == ["rev-parse", "HEAD"]:
    print(os.environ["OBSERVED_POLICY"])
elif args == ["-C", "source", "rev-parse", "HEAD"]:
    print(os.environ["OBSERVED_CHECKOUT"])
elif args[:1] == ["ls-remote"]:
    print(os.environ["OBSERVED_MAIN"] + "\\trefs/heads/main")
elif args == ["init", "-q", "source"]:
    pathlib.Path("source").mkdir()
elif args[:4] == ["-C", "source", "remote", "add"]:
    pass
elif args[:3] == ["-C", "source", "fetch"]:
    if args != ["-C", "source", "fetch", "--depth=1", "origin", os.environ["REQUESTED_SOURCE_SHA"]]:
        raise SystemExit("floating or substituted source fetch")
elif args[:3] == ["-C", "source", "checkout"]:
    pathlib.Path("source/space").mkdir()
    pathlib.Path("source/space/Dockerfile").write_text("COPY SOURCE_GITHUB_SHA /app/SOURCE_GITHUB_SHA\\n")
else:
    raise SystemExit("unreviewed Git command: " + repr(args))
''')
            fake.chmod(0o755)
            env = {**context(), **(event or {}), "REQUESTED_SOURCE_SHA": requested,
                   "OBSERVED_POLICY": POLICY, "OBSERVED_CHECKOUT": checkout, "OBSERVED_MAIN": main,
                   "GIT_CALLS": str(root / "calls"), "GITHUB_OUTPUT": str(root / "output"),
                   "GITHUB_STEP_SUMMARY": str(root / "summary"), "HOME": str(root),
                   "PATH": str(binary) + ":" + str(Path(sys.executable).parent) + ":/usr/bin:/bin"}
            result = subprocess.run(["/bin/bash", "-c", step["run"]], cwd=root, env=env,
                                    text=True, capture_output=True, timeout=15)
            calls = ([json.loads(line) for line in (root / "calls").read_text().splitlines()]
                     if (root / "calls").exists() else [])
            return result, calls, (root / "output").read_text() if (root / "output").exists() else ""

    def test_preapproval_actual_shell_binds_fetch_and_output_to_request(self):
        step = next(s for s in workflow()["jobs"]["validate"]["steps"] if s.get("id") == "source_ref")
        result, calls, output = self.run_step(step)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("sha=" + A + "\n", output)
        self.assertIn(["-C", "source", "fetch", "--depth=1", "origin", A], calls)

    def test_actual_shell_invalid_inputs_and_context_stop_before_fetch(self):
        step = next(s for s in workflow()["jobs"]["validate"]["steps"] if s.get("id") == "source_ref")
        cases = [("", None), ("main", None), ("A" * 40, None),
                 (A + "; touch SHOULD_NOT_EXIST", None), ("$(exit 0)", None),
                 (A, {"GITHUB_EVENT_NAME": "push"}), (A, {"GITHUB_REPOSITORY": "fork/.github"}),
                 (A, {"GITHUB_REF": "refs/heads/topic"}), (A, {"GITHUB_REF_PROTECTED": "false"})]
        for requested, event in cases:
            with self.subTest(requested=requested, event=event):
                result, calls, output = self.run_step(step, requested=requested, event=event)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(any("fetch" in call for call in calls))
                self.assertEqual("", output)

    def test_actual_shell_rejects_stale_and_substituted_source_before_approval(self):
        step = next(s for s in workflow()["jobs"]["validate"]["steps"] if s.get("id") == "source_ref")
        for main, checkout in ((B, A), (A, B)):
            result, _, output = self.run_step(step, main=main, checkout=checkout)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("", output)

    def test_postapproval_fetch_uses_approved_sha_and_rejects_new_main(self):
        step = next(s for s in workflow()["jobs"]["publish"]["steps"] if s.get("id") == "source_ref")
        result, calls, output = self.run_step(step, main=B)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(["-C", "source", "fetch", "--depth=1", "origin", A], calls)
        self.assertEqual("", output)

    def test_actual_last_precredential_check_rejects_approval_that_went_stale(self):
        step = next(s for s in workflow()["jobs"]["publish"]["steps"] if s.get("id") == "freshness")
        good, _, _ = self.run_step(step)
        stale, calls, _ = self.run_step(step, main=B)
        self.assertEqual(0, good.returncode, good.stderr)
        self.assertNotEqual(0, stale.returncode)
        self.assertIn("stale release", stale.stderr)
        self.assertFalse(any("fetch" in call for call in calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
