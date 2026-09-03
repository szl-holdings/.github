#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Harden review-state and classification convergence before operator admission."""
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

    old_reviews = (
        "    def reviews(self, full_name: str, number: int) -> list[str]:\n"
        "        result, _headers, _status = self.request(\n"
        "            \"GET\", f\"/repos/{full_name}/pulls/{number}/reviews?per_page=100\"\n"
        "        )\n"
        "        latest: dict[str, str] = {}\n"
        "        for row in result if isinstance(result, list) else []:\n"
        "            login = str((row.get(\"user\") or {}).get(\"login\") or \"\")\n"
        "            state = str(row.get(\"state\") or \"\")\n"
        "            if login and state:\n"
        "                latest[login] = state\n"
        "        return sorted(login for login, state in latest.items() if state == \"CHANGES_REQUESTED\")\n"
    )
    new_reviews = (
        "    def reviews(self, full_name: str, number: int) -> list[str]:\n"
        "        result, _headers, _status = self.request(\n"
        "            \"GET\", f\"/repos/{full_name}/pulls/{number}/reviews?per_page=100\"\n"
        "        )\n"
        "        # COMMENTED and PENDING reviews do not revoke an earlier change\n"
        "        # request. Only a later APPROVED or DISMISSED decision clears it.\n"
        "        latest_decisive: dict[str, str] = {}\n"
        "        decisive = {\"CHANGES_REQUESTED\", \"APPROVED\", \"DISMISSED\"}\n"
        "        for row in result if isinstance(result, list) else []:\n"
        "            login = str((row.get(\"user\") or {}).get(\"login\") or \"\")\n"
        "            state = str(row.get(\"state\") or \"\").upper()\n"
        "            if login and state in decisive:\n"
        "                latest_decisive[login] = state\n"
        "        return sorted(\n"
        "            login\n"
        "            for login, state in latest_decisive.items()\n"
        "            if state == \"CHANGES_REQUESTED\"\n"
        "        )\n"
    )
    source = replace_once(source, old_reviews, new_reviews, "decisive review state")

    old_classification_method = (
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
    new_classification_method = (
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
        "        current = [name for name in existing_labels if name]\n"
        "        preserved = [name for name in current if not name.startswith(\"estate:\")]\n"
        "        labels = sorted(set([*preserved, label]))\n"
        "        if sorted(set(current)) == labels:\n"
        "            return\n"
        "        self.ensure_label(full_name, label)\n"
        "        self.request(\n"
        "            \"PATCH\",\n"
        "            f\"/repos/{full_name}/issues/{number}\",\n"
        "            {\"labels\": labels},\n"
        "            expected=(200,),\n"
        "        )\n"
    )
    source = replace_once(
        source,
        old_classification_method,
        new_classification_method,
        "idempotent single classification",
    )

    old_classification = (
        "        labels = [str(label.get(\"name\") or \"\") for label in row.get(\"labels\") or []]\n"
        "        classification = classify_issue(\n"
        "            str(row.get(\"title\") or \"\"), row.get(\"body\"), labels\n"
        "        )\n"
    )
    new_classification = (
        "        labels = [str(label.get(\"name\") or \"\") for label in row.get(\"labels\") or []]\n"
        "        classification_labels = [\n"
        "            label for label in labels if not label.startswith(\"estate:\")\n"
        "        ]\n"
        "        classification = classify_issue(\n"
        "            str(row.get(\"title\") or \"\"), row.get(\"body\"), classification_labels\n"
        "        )\n"
    )
    source = replace_once(
        source,
        old_classification,
        new_classification,
        "classification independent of stale estate labels",
    )

    SOURCE_PATH.write_text(source, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    tests = TEST_PATH.read_text(encoding="utf-8")
    marker = "def test_comment_review_does_not_clear_change_request()"
    if marker not in tests:
        tests += '''\n\n\ndef test_comment_review_does_not_clear_change_request() -> None:\n    api = operator.GitHub(\"test-token\", apply=False)\n    api.request = mock.Mock(\n        return_value=(\n            [\n                {\"user\": {\"login\": \"reviewer\"}, \"state\": \"CHANGES_REQUESTED\"},\n                {\"user\": {\"login\": \"reviewer\"}, \"state\": \"COMMENTED\"},\n            ],\n            {},\n            200,\n        )\n    )\n    assert api.reviews(\"szl-holdings/example\", 7) == [\"reviewer\"]\n\n\ndef test_approval_clears_prior_change_request() -> None:\n    api = operator.GitHub(\"test-token\", apply=False)\n    api.request = mock.Mock(\n        return_value=(\n            [\n                {\"user\": {\"login\": \"reviewer\"}, \"state\": \"CHANGES_REQUESTED\"},\n                {\"user\": {\"login\": \"reviewer\"}, \"state\": \"APPROVED\"},\n            ],\n            {},\n            200,\n        )\n    )\n    assert api.reviews(\"szl-holdings/example\", 7) == []\n\n\ndef test_stale_estate_label_does_not_drive_reclassification() -> None:\n    api = mock.create_autospec(operator.GitHub, instance=True)\n    api.apply = True\n    api.search.return_value = [\n        {\n            \"repository_url\": \"https://api.github.com/repos/szl-holdings/example\",\n            \"number\": 11,\n            \"title\": \"Fix documentation link\",\n            \"body\": \"Update the README documentation and exact local link contract with no protected-state mutation.\",\n            \"html_url\": \"https://github.com/szl-holdings/example/issues/11\",\n            \"updated_at\": \"2026-09-02T00:00:00Z\",\n            \"labels\": [{\"name\": \"estate:p0\"}],\n        }\n    ]\n    rows = operator.reconcile_issues(api, \"szl-holdings\", limit=10)\n    assert rows[0].classification == \"estate:code-actionable\"\n    api.set_classification.assert_called_once_with(\n        \"szl-holdings/example\", 11, \"estate:code-actionable\", [\"estate:p0\"]\n    )\n\n\ndef test_exact_classification_is_a_noop() -> None:\n    api = operator.GitHub(\"test-token\", apply=True)\n    api.ensure_label = mock.Mock()\n    api.request = mock.Mock()\n    api.set_classification(\n        \"szl-holdings/example\",\n        9,\n        \"estate:runtime-drift\",\n        [\"estate:runtime-drift\", \"bug\"],\n    )\n    api.ensure_label.assert_not_called()\n    api.request.assert_not_called()\n'''
    TEST_PATH.write_text(tests, encoding="utf-8", newline="\n")


def main() -> None:
    patch_source()
    patch_tests()
    print("frontier operator hardening patch applied")


if __name__ == "__main__":
    main()
