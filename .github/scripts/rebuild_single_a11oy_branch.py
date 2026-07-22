#!/usr/bin/env python3
"""One-shot branch repair: official Hub APIs with one canonical A11oy Space."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".github" / "scripts"
WORKFLOWS = ROOT / ".github" / "workflows"
SINGLE_COMMIT = "d11b55f24dc443bd7c44591cfc23d47e88ed363e"


def show(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{SINGLE_COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label} drifted; missing {old!r}")
    return text.replace(old, new, 1)


def restore_single_space() -> None:
    (SCRIPTS / "hf_estate_canonicalize.py").write_text(
        show(".github/scripts/hf_estate_canonicalize.py"), encoding="utf-8", newline="\n"
    )
    (SCRIPTS / "test_hf_estate_canonicalize.py").write_text(
        show(".github/scripts/test_hf_estate_canonicalize.py"),
        encoding="utf-8",
        newline="\n",
    )


def hard_disable_legacy_clones() -> None:
    path = SCRIPTS / "hf_estate_upgrade.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "- creates/refreshes four private CPU-basic clones of the flagship a11oy Space;\n",
        "- enforces a single canonical A11oy Space; clone creation is disabled;\n",
    )
    text, count = re.subn(
        r'CLONE_IDS = \[f"\{ORG\}/a11oy-clone-\{index\}" for index in range\(1, 5\)\]',
        "CLONE_IDS: list[str] = []",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("could not clear legacy CLONE_IDS")
    no_clone = '''    def create_or_refresh_clones(self) -> None:
        """Permanent no-clone policy for the canonical A11oy estate."""
        self.record(
            FLAGSHIP_SPACE,
            "a11oy-clone-policy",
            "ok",
            "disabled: use branches, pull requests, or expiring previews",
        )

'''
    text, count = re.subn(
        r"    def create_or_refresh_clones\(self\) -> None:\n.*?(?=    def _ensure_collection)",
        no_clone,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not replace legacy clone creator")
    path.write_text(text, encoding="utf-8", newline="\n")


def add_pre_delete_route_verification() -> None:
    path = SCRIPTS / "hf_estate_canonicalize.py"
    text = path.read_text(encoding="utf-8")
    text = replace(
        text,
        "import time\nfrom datetime import datetime, timezone",
        "import time\nfrom datetime import datetime, timezone\n\nimport requests",
        "canonical requests import",
    )
    constants = '''
PUBLIC_APP_BASE = "https://szlholdings-a11oy.hf.space"
PUBLIC_ROUTE_SPECS = (
    ("process-liveness", "/api/livez", {"status": "LIVE"}),
    ("build-identity", "/api/build-info", {"status": "OBSERVED"}),
    (
        "receipt-verifier",
        "/api/a11oy/v1/verify/receipt",
        {"schema": "szl.public-receipt-verifier/manifest/v1"},
    ),
)
BUILD_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

'''
    text = replace(
        text,
        "# Permanent kill switch for the inherited clone creator and collection additions.\n",
        constants
        + "# Permanent kill switch for the inherited clone creator and collection additions.\n",
        "canonical route constants",
    )
    method = r'''
    def _verify_public_routes(self, timeout_seconds: int = 600) -> None:
        self.route_validation: dict[str, dict[str, Any]] = {}
        if not self.publish:
            for route_id, route_path, expected in PUBLIC_ROUTE_SPECS:
                self.route_validation[route_id] = {
                    "url": f"{PUBLIC_APP_BASE}{route_path}",
                    "expected": expected,
                    "state": "PLANNED",
                }
                self.record(
                    f"{PUBLIC_APP_BASE}{route_path}",
                    f"public-route:{route_id}",
                    "dry-run",
                )
            return

        session = requests.Session()
        session.headers.update(
            {
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": "szl-single-a11oy-post-deploy/1",
            }
        )
        deadline = time.monotonic() + timeout_seconds
        last_errors: list[str] = []
        while True:
            last_errors = []
            observations: dict[str, dict[str, Any]] = {}
            for route_id, route_path, expected in PUBLIC_ROUTE_SPECS:
                url = f"{PUBLIC_APP_BASE}{route_path}"
                try:
                    response = session.get(url, timeout=45, allow_redirects=True)
                    if response.status_code != 200:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise RuntimeError("response is not a JSON object")
                    mismatches = {
                        key: {"expected": value, "observed": payload.get(key)}
                        for key, value in expected.items()
                        if payload.get(key) != value
                    }
                    if mismatches:
                        raise RuntimeError(f"marker mismatch: {mismatches}")
                    if route_id == "build-identity":
                        build = payload.get("build") or {}
                        revision = str(build.get("revision") or "")
                        if build.get("state") != "OBSERVED" or not BUILD_SHA_RE.fullmatch(
                            revision
                        ):
                            raise RuntimeError(
                                f"build identity is not an observed immutable SHA: {build}"
                            )
                    observations[route_id] = {
                        "url": url,
                        "http_status": response.status_code,
                        "state": "VALIDATED",
                    }
                except Exception as exc:  # noqa: BLE001
                    last_errors.append(f"{route_id}:{type(exc).__name__}:{exc}")
            if not last_errors:
                self.route_validation = observations
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Canonical public-route verification did not converge: "
                    + "; ".join(last_errors)
                )
            time.sleep(15)

        for route_id, route_path, _expected in PUBLIC_ROUTE_SPECS:
            self.record(
                f"{PUBLIC_APP_BASE}{route_path}",
                f"public-route:{route_id}",
                "validated",
            )

'''
    text = replace(
        text,
        "    def _remove_collection_references(self) -> None:\n",
        method + "    def _remove_collection_references(self) -> None:\n",
        "canonical route method",
    )
    text = replace(
        text,
        "            self._verify_adopted_file_set(selected[\"repo_id\"])\n",
        "            self._verify_adopted_file_set(selected[\"repo_id\"])\n"
        "            self._verify_public_routes()\n",
        "canonical route call",
    )
    text = replace(
        text,
        "        report[\"adoption_plan\"] = getattr(self, \"adoption_plan\", {})\n",
        "        report[\"adoption_plan\"] = getattr(self, \"adoption_plan\", {})\n"
        "        report[\"route_validation\"] = getattr(self, \"route_validation\", {})\n"
        "        report[\"clone_creation_enabled\"] = False\n",
        "canonical route report",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def convert_official_v2() -> None:
    path = SCRIPTS / "hf_estate_command_centers_v2.py"
    text = path.read_text(encoding="utf-8")
    marker = "from __future__ import annotations"
    _, rest = text.split(marker, 1)
    text = '''#!/usr/bin/env python3
"""Official-API estate verification with one canonical A11oy Space.

The publisher inherits the fail-closed newest-content adoption, byte-level
parity, public route verification, collection cleanup, and exact clone deletion
contract from ``hf_estate_canonicalize.SingleA11oyEstateUpgrade``. It adds
supported Hub API inventory/readback for collections and buckets.
"""
''' + marker + rest
    text = replace(
        text,
        "class CommandCenterEstateUpgradeV2(command_centers.CommandCenterEstateUpgrade):",
        "class SingleA11oyEstateUpgradeV2(command_centers.SingleA11oyEstateUpgrade):",
        "v2 base class",
    )
    text = replace(
        text,
        '"""Full estate maintenance with official Collections and Buckets APIs."""',
        '"""Official-API estate maintenance with one canonical A11oy Space."""',
        "v2 class docstring",
    )
    text, count = re.subn(
        r"\n    def _create_missing_clone\(self, clone_id: str\) -> None:\n.*?(?=    def _collection_item_resolves)",
        "\n    def _collection_item_resolves",
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not remove v2 clone creation method")
    text = replace(
        text,
        "            unresolved: list[str] = []\n            resolved = 0",
        "            unresolved: list[str] = []\n"
        "            clone_references: list[str] = []\n"
        "            resolved = 0",
        "v2 clone-reference list",
    )
    text = replace(
        text,
        "                    try:\n                        self._collection_item_resolves(item_type, item_id)",
        '''                    if (
                        item_type == "space"
                        and item_id in command_centers.HISTORICAL_CLONE_IDS
                    ):
                        clone_references.append(item_id)
                        continue
                    try:
                        self._collection_item_resolves(item_type, item_id)''',
        "v2 clone-reference detection",
    )
    text = replace(
        text,
        '                    "unresolved_items": unresolved,\n                    "private":',
        '                    "unresolved_items": unresolved,\n'
        '                    "clone_references": clone_references,\n'
        '                    "private":',
        "v2 collection snapshot",
    )
    old = '''                if unresolved:
                    self.record(
                        slug,
                        "collection-resolution",
                        "error",
                        f"title={title}; unresolved={unresolved[:20]}",
                    )
                else:
                    self.record(
                        slug,
                        "collection-resolution",
                        "validated",
                        f"title={title}; resolving_items={resolved}",
                    )'''
    new = '''                if unresolved:
                    self.record(
                        slug,
                        "collection-resolution",
                        "error",
                        f"title={title}; unresolved={unresolved[:20]}",
                    )
                elif clone_references and self.publish:
                    self.record(
                        slug,
                        "collection-resolution",
                        "error",
                        f"title={title}; clone_references={clone_references}",
                    )
                elif clone_references:
                    self.record(
                        slug,
                        "collection-resolution",
                        "dry-run",
                        f"title={title}; planned_clone_removals={clone_references}",
                    )
                else:
                    self.record(
                        slug,
                        "collection-resolution",
                        "validated",
                        f"title={title}; resolving_items={resolved}; clones=0",
                    )'''
    text = replace(text, old, new, "v2 collection resolution")
    text = replace(
        text,
        '        report["inventory_contract"] = "huggingface_hub-supported-api/v2"',
        '        report["inventory_contract"] = "huggingface_hub-supported-api/v2"\n'
        '        report["clone_creation_enabled"] = False',
        "v2 clone policy report",
    )
    text = replace(
        text,
        "CommandCenterEstateUpgradeV2(\n",
        "SingleA11oyEstateUpgradeV2(\n",
        "v2 main class",
    )
    text = replace(
        text,
        "\ndef main() -> int:",
        "\n\nCommandCenterEstateUpgradeV2 = SingleA11oyEstateUpgradeV2\n\n\ndef main() -> int:",
        "v2 compatibility alias",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    path = SCRIPTS / "test_hf_estate_command_centers_v2.py"
    text = path.read_text(encoding="utf-8").replace(
        "object.__new__(v2.CommandCenterEstateUpgradeV2)",
        "object.__new__(v2.SingleA11oyEstateUpgradeV2)",
    )
    new_test = '''    def test_clone_creation_is_permanently_disabled(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_command_centers_v2.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(v2.legacy.CLONE_IDS, [])
        for forbidden in (
            "duplicate_repo(",
            "duplicate_space(",
            "_create_missing_clone",
            "space_hardware=",
        ):
            self.assertNotIn(forbidden, source)
        canonical = (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("retire-a11oy-clone", canonical)
        self.assertIn("public-route:process-liveness", canonical)

'''
    text, count = re.subn(
        r"    def test_clone_creation_uses_no_custom_sleep_time\(self\) -> None:\n.*?(?=    def test_every_collection_item_type_is_read_back)",
        new_test,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("could not replace v2 clone test")
    old = '''        self.assertIn("hf_estate_command_centers_v2.py", workflow)
        self.assertIn("test_hf_estate_command_centers_v2.py", workflow)
        self.assertIn("HF_ORG_TOKEN1", workflow)
        self.assertIn('"huggingface_hub>=1.10,<2"', workflow)'''
    new = '''        self.assertIn("hf_estate_command_centers_v2.py", workflow)
        self.assertIn("test_hf_estate_command_centers_v2.py", workflow)
        self.assertIn("HF_ORG_TOKEN1", workflow)
        self.assertIn('"huggingface_hub>=1.10,<2"', workflow)
        self.assertIn("sole persistent governed A11oy Space", workflow)
        self.assertNotIn("managed_clone_ids", workflow)
        self.assertNotIn("Retained command center", workflow)'''
    text = replace(text, old, new, "v2 workflow test")
    path.write_text(text, encoding="utf-8", newline="\n")

    path = SCRIPTS / "test_hf_estate_canonicalize.py"
    text = path.read_text(encoding="utf-8")
    text = replace(
        text,
        '        self.assertIn("hf_estate_canonicalize.py", workflow)',
        '''        self.assertIn("hf_estate_command_centers_v2.py", workflow)
        self.assertNotIn(
            "python .github/scripts/hf_estate_canonicalize.py", workflow
        )''',
        "single workflow test",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_workflow() -> None:
    path = WORKFLOWS / "hf-estate-upgrade.yml"
    text = path.read_text(encoding="utf-8")
    changes = {
        "name: HF Estate — Official API Command Centers":
            "name: HF Estate — Single Canonical A11oy",
        "# Space, four public synchronized command centers, and complete official-API":
            "# Space, permanent clone retirement, and complete official-API",
        "REPORT_ISSUE_TITLE: '[hf-estate-report] official API command centers'":
            "REPORT_ISSUE_TITLE: '[hf-estate-report] single canonical A11oy'",
        '"managed_clone_ids": [': '"retired_clone_ids": [',
        "Verify command-center and official-API contracts":
            "Verify single-Space and official-API contracts",
        "Official-API publish reconciliation completed with zero recorded errors.":
            "Single-A11oy official-API reconciliation completed with zero recorded errors.",
        "## Hugging Face estate — official API":
            "## Hugging Face estate — one canonical A11oy",
    }
    for old, new in changes.items():
        text = replace(text, old, new, f"workflow {old}")
    text = replace(
        text,
        "name: HF Estate — Single Canonical A11oy\n\n",
        "name: HF Estate — Single Canonical A11oy\n\n"
        "# The sole governed A11oy Space is the sole persistent governed A11oy Space.\n",
        "workflow doctrine",
    )
    start = text.index('                   clones = report.get("managed_clone_snapshots", {})')
    end_marker = '                   out.write("\\n| Inventory | Count |\\n|---|---:|\\n")'
    end = text.index(end_marker, start)
    summary = '''                   retired = report.get("retired_clone_ids", [])
                   out.write(
                       f"Retired A11oy clones: {len(retired)} "
                       f"(creation enabled: {report.get('clone_creation_enabled')})\\n\\n"
                   )
'''
    text = text[:start] + summary + text[end:]
    text = text.replace("official API command centers", "single canonical A11oy")
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    restore_single_space()
    hard_disable_legacy_clones()
    add_pre_delete_route_verification()
    convert_official_v2()
    patch_tests()
    patch_workflow()


if __name__ == "__main__":
    main()
