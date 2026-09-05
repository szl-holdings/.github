#!/usr/bin/env python3
"""One-shot forward repair for the estate organization-card source-binding P1."""
from __future__ import annotations

import json
from pathlib import Path


CONTROLLER = Path(".github/scripts/estate_alignment_contract.py")
TESTS = Path(".github/scripts/test_estate_alignment_contract.py")
CONTRACT = Path("docs/ESTATE_ALIGNMENT_CONTRACT_V1.json")
WORKCELL = Path("audit/ESTATE_ALIGNMENT_CURRENT_MAIN_SUCCESSOR_2026-09-05.md")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one target, found {count}")
    return text.replace(old, new, 1)


def patch_controller() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'RUNTIME_BINDING_PATHS = ("/api/build-info", "/deployment.json")\n',
        '''RUNTIME_BINDING_PATHS = ("/api/build-info", "/deployment.json")
ORG_CARD_SPACE_ID = "SZLHOLDINGS/README"
ORG_CARD_RUNTIME_ORIGIN = "https://szlholdings-readme.static.hf.space"
ORG_CARD_DEPLOYMENT_SOURCE = "szl-holdings/.github"
ORG_CARD_BINDING_PATHS = ("/deployment.json",)
''',
        label="organization-card constants",
    )

    validation_anchor = '''        require(snapshot.get("organization_card_space_excluded_from_portfolio_count") == "SZLHOLDINGS/README", "README control-surface exclusion missing", failures)

    movement = contract.get("movement_contract")
'''
    validation_replacement = '''        require(snapshot.get("organization_card_space_excluded_from_portfolio_count") == ORG_CARD_SPACE_ID, "README control-surface exclusion missing", failures)

    org_card = contract.get("organization_card_control_surface")
    require(isinstance(org_card, dict), "organization_card_control_surface must be an object", failures)
    if isinstance(org_card, dict):
        require(org_card.get("repo_id") == ORG_CARD_SPACE_ID, "organization-card repo_id mismatch", failures)
        require(org_card.get("class") == "organization_card_control_surface", "organization-card class mismatch", failures)
        require(org_card.get("deployment_source") == ORG_CARD_DEPLOYMENT_SOURCE, "organization-card deployment source mismatch", failures)
        require(org_card.get("runtime_origin") == ORG_CARD_RUNTIME_ORIGIN, "organization-card runtime origin mismatch", failures)
        require(org_card.get("binding_paths") == list(ORG_CARD_BINDING_PATHS), "organization-card binding path mismatch", failures)
        require(org_card.get("portfolio_member") is False, "organization-card must remain outside the portfolio count", failures)
        require(
            org_card.get("claim_boundary")
            == "Source-bound organization front door; excluded from the 16 portfolio-Space count.",
            "organization-card claim boundary mismatch",
            failures,
        )

    movement = contract.get("movement_contract")
'''
    text = replace_once(
        text,
        validation_anchor,
        validation_replacement,
        label="organization-card contract validation",
    )

    binding_anchor = '''    origin = runtime_origin(repo_id)
    attempts: list[dict[str, Any]] = []
    for path in RUNTIME_BINDING_PATHS:
'''
    binding_replacement = '''    if repo_id == ORG_CARD_SPACE_ID:
        configured_origin = str(row.get("runtime_origin") or "")
        if configured_origin != ORG_CARD_RUNTIME_ORIGIN:
            raise AlignmentError(
                f"organization-card runtime origin mismatch: {configured_origin!r}"
            )
        configured_paths = row.get("binding_paths")
        if configured_paths != list(ORG_CARD_BINDING_PATHS):
            raise AlignmentError(
                f"organization-card binding paths mismatch: {configured_paths!r}"
            )
        origin = ORG_CARD_RUNTIME_ORIGIN
        binding_paths = ORG_CARD_BINDING_PATHS
    else:
        if row.get("runtime_origin") is not None or row.get("binding_paths") is not None:
            raise AlignmentError(
                f"custom runtime binding is reserved for {ORG_CARD_SPACE_ID}"
            )
        origin = runtime_origin(repo_id)
        binding_paths = RUNTIME_BINDING_PATHS
    attempts: list[dict[str, Any]] = []
    for path in binding_paths:
'''
    text = replace_once(
        text,
        binding_anchor,
        binding_replacement,
        label="organization-card runtime binding selection",
    )

    text = replace_once(
        text,
        '    portfolio_ids = space_ids - {"SZLHOLDINGS/README"}\n',
        '    portfolio_ids = space_ids - {ORG_CARD_SPACE_ID}\n',
        label="organization-card portfolio exclusion",
    )
    text = replace_once(
        text,
        '    require("SZLHOLDINGS/README" in space_ids, "Hugging Face organization-card Space missing", failures)\n',
        '    require(ORG_CARD_SPACE_ID in space_ids, "Hugging Face organization-card Space missing", failures)\n',
        label="organization-card presence constant",
    )

    return_anchor = '''    runtime_bindings: list[dict[str, Any]] = []
    for _, observation, failure in sorted(runtime_results):
        if observation is not None:
            runtime_bindings.append(observation)
        if failure is not None:
            failures.append(failure)
    return failures, {
        "a11oy_contract_revision": a11oy_sha,
        "canonical_repositories": repository_observations,
        "runtime_source_bindings": runtime_bindings,
'''
    return_replacement = '''    runtime_bindings: list[dict[str, Any]] = []
    for _, observation, failure in sorted(runtime_results):
        if observation is not None:
            runtime_bindings.append(observation)
        if failure is not None:
            failures.append(failure)

    org_card_binding: dict[str, Any] | None = None
    org_card = contract.get("organization_card_control_surface")
    if not isinstance(org_card, Mapping):
        failures.append("organization-card source contract unavailable")
    else:
        org_card_repository = source_repository(org_card.get("deployment_source"))
        org_card_revision = repository_revisions.get(org_card_repository)
        if org_card_revision is None:
            failures.append(
                f"organization-card source authority unavailable: {org_card_repository}"
            )
        else:
            try:
                org_card_binding = runtime_source_binding(org_card, org_card_revision)
            except Exception as exc:
                failures.append(
                    "organization-card source binding unavailable: "
                    f"{type(exc).__name__}"
                )
            else:
                if org_card_binding.get("matched") is not True:
                    failures.append(
                        "organization-card source revision drift: "
                        f"expected {org_card_repository}@{org_card_revision}, observed "
                        f"{org_card_binding.get('observed_source')}@"
                        f"{org_card_binding.get('observed_revision')}"
                    )

    return failures, {
        "a11oy_contract_revision": a11oy_sha,
        "canonical_repositories": repository_observations,
        "runtime_source_bindings": runtime_bindings,
        "organization_card_source_binding": org_card_binding,
'''
    text = replace_once(
        text,
        return_anchor,
        return_replacement,
        label="organization-card live evidence",
    )

    CONTROLLER.write_text(text, encoding="utf-8")


def patch_contract() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    movement = contract.pop("movement_contract")
    contract["organization_card_control_surface"] = {
        "repo_id": "SZLHOLDINGS/README",
        "class": "organization_card_control_surface",
        "deployment_source": "szl-holdings/.github",
        "runtime_origin": "https://szlholdings-readme.static.hf.space",
        "binding_paths": ["/deployment.json"],
        "portfolio_member": False,
        "claim_boundary": "Source-bound organization front door; excluded from the 16 portfolio-Space count.",
    }
    contract["movement_contract"] = movement
    CONTRACT.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''        self.assertEqual(set(seen), alignment.EXPECTED_PORTFOLIO_SPACES)
        self.assertEqual(len(observation["runtime_source_bindings"]), 16)
''',
        '''        self.assertEqual(
            set(seen),
            alignment.EXPECTED_PORTFOLIO_SPACES | {alignment.ORG_CARD_SPACE_ID},
        )
        self.assertEqual(len(observation["runtime_source_bindings"]), 16)
        self.assertEqual(
            observation["organization_card_source_binding"]["repo_id"],
            alignment.ORG_CARD_SPACE_ID,
        )
''',
        label="live org-card test expectation",
    )

    marker = '''

if __name__ == "__main__":
    unittest.main()
'''
    methods = '''

    def test_org_card_contract_is_exact_and_outside_portfolio_count(self) -> None:
        org_card = self.contract["organization_card_control_surface"]
        self.assertEqual(org_card["repo_id"], alignment.ORG_CARD_SPACE_ID)
        self.assertEqual(
            org_card["deployment_source"], alignment.ORG_CARD_DEPLOYMENT_SOURCE
        )
        self.assertEqual(org_card["runtime_origin"], alignment.ORG_CARD_RUNTIME_ORIGIN)
        self.assertEqual(org_card["binding_paths"], list(alignment.ORG_CARD_BINDING_PATHS))
        self.assertIs(org_card["portfolio_member"], False)
        portfolio_ids = {
            row["repo_id"]
            for row in self.contract["huggingface_inventory_snapshot"]["portfolio_spaces"]
        }
        self.assertEqual(len(portfolio_ids), 16)
        self.assertNotIn(alignment.ORG_CARD_SPACE_ID, portfolio_ids)

    def test_org_card_runtime_binding_uses_static_deployment_receipt_only(self) -> None:
        expected = "a" * 40
        requested: list[tuple[str, str | None]] = []

        def fetch(url: str, **kwargs) -> bytes:
            requested.append((url, kwargs.get("required_origin")))
            return json.dumps(
                {
                    "source": {
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": expected,
                    }
                }
            ).encode()

        observation = alignment.runtime_source_binding(
            self.contract["organization_card_control_surface"],
            expected,
            fetch=fetch,
        )

        self.assertTrue(observation["matched"])
        self.assertEqual(observation["binding_path"], "/deployment.json")
        self.assertEqual(len(requested), alignment.RUNTIME_OBSERVATIONS)
        for url, required_origin in requested:
            parsed = alignment.urllib.parse.urlsplit(url)
            self.assertEqual(parsed.netloc, "szlholdings-readme.static.hf.space")
            self.assertEqual(parsed.path, "/deployment.json")
            self.assertEqual(required_origin, alignment.ORG_CARD_RUNTIME_ORIGIN)

    def test_org_card_binding_fails_closed_on_stale_conflicting_or_redirected_evidence(self) -> None:
        expected = "b" * 40
        row = self.contract["organization_card_control_surface"]

        stale = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source": {
                        "repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                        "revision": "c" * 40,
                    }
                }
            ).encode(),
        )
        self.assertFalse(stale["matched"])

        conflicting = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: json.dumps(
                {
                    "source_repository": alignment.ORG_CARD_DEPLOYMENT_SOURCE,
                    "source_revision": expected,
                    "build": {"revision": "d" * 40},
                }
            ).encode(),
        )
        self.assertFalse(conflicting["matched"])

        redirected = alignment.runtime_source_binding(
            row,
            expected,
            fetch=lambda _url, **_kwargs: (_ for _ in ()).throw(
                alignment.AlignmentError("cross-origin redirect rejected")
            ),
        )
        self.assertFalse(redirected["matched"])

    def test_org_card_contract_rejects_wrong_origin_and_membership(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["organization_card_control_surface"]["runtime_origin"] = (
            "https://szlholdings-readme.hf.space"
        )
        candidate["organization_card_control_surface"]["portfolio_member"] = True
        failures = alignment.validate_contract(candidate)
        self.assertIn("organization-card runtime origin mismatch", failures)
        self.assertIn(
            "organization-card must remain outside the portfolio count", failures
        )
'''
    text = replace_once(
        text,
        marker,
        methods + marker,
        label="organization-card adversarial tests",
    )
    TESTS.write_text(text, encoding="utf-8")


def patch_workcell() -> None:
    text = WORKCELL.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "- `state`: `OPEN_REPAIR`",
        "- `state`: `IMPLEMENTED_PENDING_EXACT_HEAD_CI`",
        label="workcell state",
    )
    appendix = '''

## Forward implementation

The current-main successor now treats `SZLHOLDINGS/README` as a separate,
source-bound control surface. Its only accepted runtime evidence is
`https://szlholdings-readme.static.hf.space/deployment.json`, observed twice
with cache-busting and constrained to the same origin, and it must match the
exact protected-main revision of `szl-holdings/.github`.

The evidence is emitted separately as `organization_card_source_binding`;
`runtime_source_bindings` remains exactly the 16 portfolio Spaces. Focused
regressions cover stale revisions, conflicting revisions, cross-origin
failures, the static-host path, and count preservation. This is not a merge or
live-deployment claim; exact-head CI and protected review remain required.
'''
    if "## Forward implementation" in text:
        raise SystemExit("workcell forward implementation already present")
    WORKCELL.write_text(text.rstrip() + appendix + "\n", encoding="utf-8")


def main() -> int:
    patch_controller()
    patch_contract()
    patch_tests()
    patch_workcell()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
