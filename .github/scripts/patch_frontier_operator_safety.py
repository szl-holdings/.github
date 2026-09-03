#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply fail-closed safety corrections to the frontier issue operator candidate."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / ".github" / "scripts" / "frontier_issue_operator.py"
TEST_PATH = ROOT / "tests" / "test_frontier_issue_operator.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one old block, found {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    source = SOURCE_PATH.read_text(encoding="utf-8")

    old_add_label = (
        "    def add_label(self, full_name: str, number: int, label: str) -> None:\n"
        "        if not self.apply:\n"
        "            return\n"
        "        self.ensure_label(full_name, label)\n"
        "        self.request(\n"
        "            \"POST\",\n"
        "            f\"/repos/{full_name}/issues/{number}/labels\",\n"
        "            {\"labels\": [label]},\n"
        "            expected=(200,),\n"
        "        )\n"
    )
    new_set_classification = (
        "    def set_classification(\n"
        "        self,\n"
        "        full_name: str,\n"
        "        number: int,\n"
        "        label: str,\n"
        "        existing_labels: Iterable[str],\n"
        "    ) -> None:\n"
        "        \"\"\"Preserve human labels while enforcing exactly one estate label.\"\"\"\n"
        "        if not self.apply:\n"
        "            return\n"
        "        self.ensure_label(full_name, label)\n"
        "        preserved = [\n"
        "            name\n"
        "            for name in existing_labels\n"
        "            if name and not name.startswith(\"estate:\")\n"
        "        ]\n"
        "        labels = sorted(set([*preserved, label]))\n"
        "        self.request(\n"
        "            \"PATCH\",\n"
        "            f\"/repos/{full_name}/issues/{number}\",\n"
        "            {\"labels\": labels},\n"
        "            expected=(200,),\n"
        "        )\n"
    )
    source = replace_once(
        source,
        old_add_label,
        new_set_classification,
        "single estate-label enforcement",
    )

    old_command_center = (
        "        result, _headers, _status = self.request(\n"
        "            \"POST\",\n"
        "            f\"/repos/{org}/.github/issues\",\n"
        "            {\"title\": COMMAND_CENTER_TITLE, \"body\": body, \"labels\": [\"estate:execution-ledger\"]},\n"
        "            expected=(201,),\n"
        "        )\n"
    )
    new_command_center = (
        "        self.ensure_label(f\"{org}/.github\", \"estate:execution-ledger\")\n"
        "        result, _headers, _status = self.request(\n"
        "            \"POST\",\n"
        "            f\"/repos/{org}/.github/issues\",\n"
        "            {\"title\": COMMAND_CENTER_TITLE, \"body\": body, \"labels\": [\"estate:execution-ledger\"]},\n"
        "            expected=(201,),\n"
        "        )\n"
    )
    source = replace_once(
        source,
        old_command_center,
        new_command_center,
        "command-center label admission",
    )

    old_grouping = (
        "    by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)\n"
        "    for row in raw:\n"
        "        fingerprint = issue_fingerprint(str(row.get(\"title\") or \"\"), row.get(\"body\"))\n"
        "        if fingerprint:\n"
        "            by_fingerprint[fingerprint].append(row)\n"
        "\n"
        "    canonical_for: dict[str, dict[str, Any]] = {}\n"
        "    for fingerprint, group in by_fingerprint.items():\n"
    )
    new_grouping = (
        "    # Duplicate closure is repository-local. Identical text can represent an\n"
        "    # independently valid defect when filed against two different components.\n"
        "    by_fingerprint: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)\n"
        "    for row in raw:\n"
        "        repository = repository_from_api_url(str(row[\"repository_url\"]))\n"
        "        fingerprint = issue_fingerprint(str(row.get(\"title\") or \"\"), row.get(\"body\"))\n"
        "        if fingerprint:\n"
        "            by_fingerprint[(repository, fingerprint)].append(row)\n"
        "\n"
        "    canonical_for: dict[tuple[str, str], dict[str, Any]] = {}\n"
        "    for fingerprint, group in by_fingerprint.items():\n"
    )
    source = replace_once(
        source,
        old_grouping,
        new_grouping,
        "repository-local duplicate grouping",
    )

    source = replace_once(
        source,
        "            canonical = canonical_for.get(fingerprint or \"\")\n",
        "            canonical = canonical_for.get((repository, fingerprint or \"\"))\n",
        "repository-local canonical lookup",
    )

    old_label_call = (
        "                api.add_label(repository, state.number, classification)\n"
        "                state.action = \"WOULD_CLASSIFY\" if not api.apply else \"CLASSIFIED\"\n"
    )
    new_label_call = (
        "                api.set_classification(\n"
        "                    repository, state.number, classification, labels\n"
        "                )\n"
        "                state.action = \"WOULD_CLASSIFY\" if not api.apply else \"CLASSIFIED\"\n"
    )
    source = replace_once(
        source,
        old_label_call,
        new_label_call,
        "single classification call",
    )

    SOURCE_PATH.write_text(source, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    tests = TEST_PATH.read_text(encoding="utf-8")
    tests = tests.replace(
        "assert api.add_label.call_count == 2",
        "assert api.set_classification.call_count == 2",
    )

    marker = "def test_identical_issues_in_different_repositories_are_not_closed()"
    if marker not in tests:
        tests += '''\n\n\ndef test_identical_issues_in_different_repositories_are_not_closed() -> None:\n    api = mock.create_autospec(operator.GitHub, instance=True)\n    api.apply = True\n    body = \"This exact long issue text is valid independently for two repository components.\"\n    api.search.return_value = [\n        {\n            \"repository_url\": \"https://api.github.com/repos/szl-holdings/alpha\",\n            \"number\": 1,\n            \"title\": \"Same component defect\",\n            \"body\": body,\n            \"html_url\": \"https://github.com/szl-holdings/alpha/issues/1\",\n            \"updated_at\": \"2026-09-01T00:00:00Z\",\n            \"labels\": [],\n        },\n        {\n            \"repository_url\": \"https://api.github.com/repos/szl-holdings/beta\",\n            \"number\": 1,\n            \"title\": \"Same component defect\",\n            \"body\": body,\n            \"html_url\": \"https://github.com/szl-holdings/beta/issues/1\",\n            \"updated_at\": \"2026-09-02T00:00:00Z\",\n            \"labels\": [],\n        },\n    ]\n    rows = operator.reconcile_issues(api, \"szl-holdings\", limit=10)\n    assert all(row.action == \"CLASSIFIED\" for row in rows)\n    api.close_duplicate.assert_not_called()\n    assert api.set_classification.call_count == 2\n\n\ndef test_classification_replaces_stale_estate_labels_and_preserves_human_labels() -> None:\n    api = operator.GitHub(\"test-token\", apply=True)\n    api.ensure_label = mock.Mock()\n    api.request = mock.Mock(return_value=({}, {}, 200))\n    api.set_classification(\n        \"szl-holdings/example\",\n        9,\n        \"estate:runtime-drift\",\n        [\"bug\", \"estate:backlog\", \"estate:code-actionable\"],\n    )\n    api.ensure_label.assert_called_once_with(\n        \"szl-holdings/example\", \"estate:runtime-drift\"\n    )\n    api.request.assert_called_once_with(\n        \"PATCH\",\n        \"/repos/szl-holdings/example/issues/9\",\n        {\"labels\": [\"bug\", \"estate:runtime-drift\"]},\n        expected=(200,),\n    )\n'''

    TEST_PATH.write_text(tests, encoding="utf-8", newline="\n")


def main() -> None:
    patch_source()
    patch_tests()
    print("frontier operator safety patch applied")


if __name__ == "__main__":
    main()
