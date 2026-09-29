#!/usr/bin/env python3
"""Network-free tests for hf-card/render.py, hf-card/lint.py and schema.json.

Run: python hf-card/tests/test_hf_card.py
"""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import lint  # noqa: E402
import render  # noqa: E402

FIXTURES = HERE / "fixtures"
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"
RECEIPT = f"https://github.com/szl-holdings/demo/blob/{SHA}/receipts/bench.json"

FRONT = """---
license: apache-2.0
library_name: kernels
tags: [kernel]
szl:
  source_repo: szl-holdings/demo
  proof_url: https://github.com/szl-holdings/demo
---
"""


def card(body: str, front: str = FRONT) -> str:
    return front + "\n" + body


def findings(text: str, card_type: str = "kernel") -> list[lint.Finding]:
    return lint.lint_text(text, card_type).findings


def rules(text: str, card_type: str = "kernel") -> list[str]:
    return [f.rule for f in findings(text, card_type)]


class RenderTests(unittest.TestCase):
    def test_every_fixture_renders_and_lints_clean(self) -> None:
        for path in sorted(FIXTURES.glob("*.card.yaml")):
            with self.subTest(fixture=path.name):
                data = render.load_vars(path)
                text = render.render(data, vars_path="hf/card.yaml")
                report = lint.lint_text(text, None)
                self.assertTrue(report.ok, [f.message for f in report.findings])
                self.assertEqual(report.card_type, data["type"])
                meta, _, _ = lint.split_front_matter(text)
                self.assertEqual(meta, data["front_matter"])

    def test_rendering_is_deterministic(self) -> None:
        data = render.load_vars(FIXTURES / "model.card.yaml")
        self.assertEqual(render.render(copy.deepcopy(data)), render.render(copy.deepcopy(data)))

    def test_source_sha_is_stamped_in_front_matter_and_marker(self) -> None:
        data = render.load_vars(FIXTURES / "space.card.yaml")
        text = render.render(data, source_sha=SHA)
        meta, _, _ = lint.split_front_matter(text)
        self.assertEqual(meta["szl"]["source_sha"], SHA)
        self.assertIn(f"sha={SHA}", text)
        self.assertIn(f"/commit/{SHA}", text)
        with self.assertRaises(render.VarsError):
            render.render(data, source_sha="main")

    def test_measured_claim_without_receipt_is_refused(self) -> None:
        data = render.load_vars(FIXTURES / "model.card.yaml")
        data["claims"] = [{"label": "MEASURED", "claim": "tests pass"}]
        with self.assertRaisesRegex(render.VarsError, "D10"):
            render.render(data)

    def test_receipt_must_be_pinned_and_in_source_repo(self) -> None:
        data = render.load_vars(FIXTURES / "model.card.yaml")
        for receipt in (
            "https://github.com/szl-holdings/example-model/blob/main/receipts/tests.json",
            f"https://github.com/szl-holdings/other-repo/blob/{SHA}/receipts/tests.json",
            f"https://example.com/{SHA}/tests.json",
        ):
            with self.subTest(receipt=receipt):
                data["claims"] = [{"label": "MEASURED", "claim": "tests pass", "receipt": receipt}]
                with self.assertRaises(render.VarsError):
                    render.render(data)

    def test_unknown_label_and_vars_keys_are_refused(self) -> None:
        data = render.load_vars(FIXTURES / "model.card.yaml")
        data["claims"] = [{"label": "PROVEN", "claim": "anything"}]
        with self.assertRaises(render.VarsError):
            render.render(data)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "card.yaml"
            bad.write_text("type: model\nrepo_id: SZLHOLDINGS/x\ntitle: x\nsummary: x\nfront_matter: {}\nextra: 1\n",
                           encoding="utf-8")
            with self.assertRaisesRegex(render.VarsError, "unknown vars key"):
                render.load_vars(bad)

    def test_org_casing_is_literal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "card.yaml"
            bad.write_text("type: model\nrepo_id: szlholdings/x\ntitle: x\nsummary: x\nfront_matter: {}\n",
                           encoding="utf-8")
            with self.assertRaisesRegex(render.VarsError, "SZLHOLDINGS"):
                render.load_vars(bad)

    def test_check_mode_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "README.md"
            vars_file = str(FIXTURES / "dataset.card.yaml")
            sink = io.StringIO()
            with redirect_stdout(sink), redirect_stderr(sink):
                self.assertEqual(render.main([vars_file, "--out", str(out), "--check"]), 1)
                self.assertEqual(render.main([vars_file, "--out", str(out)]), 0)
                self.assertEqual(render.main([vars_file, "--out", str(out), "--check"]), 0)
                out.write_text(out.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8")
                self.assertEqual(render.main([vars_file, "--out", str(out), "--check"]), 1)

    def test_template_supplies_no_license(self) -> None:
        data = render.load_vars(FIXTURES / "dataset.card.yaml")
        del data["front_matter"]["license"]
        with self.assertRaisesRegex(render.VarsError, "license"):
            render.render(data)


class SchemaTests(unittest.TestCase):
    def meta(self, card_type: str) -> dict:
        return copy.deepcopy(render.load_vars(FIXTURES / f"{card_type}.card.yaml")["front_matter"])

    def test_fixtures_validate(self) -> None:
        for card_type in lint.CARD_TYPES:
            with self.subTest(card_type=card_type):
                self.assertEqual(lint.validate_front_matter(self.meta(card_type), card_type), [])

    def test_required_fields(self) -> None:
        cases = [
            ("model", "library_name"),
            ("model", "tags"),
            ("dataset", "szl"),
            ("space", "sdk"),
            ("kernel", "license"),
        ]
        for card_type, key in cases:
            with self.subTest(card_type=card_type, key=key):
                meta = self.meta(card_type)
                del meta[key]
                self.assertTrue(any(key in e for e in lint.validate_front_matter(meta, card_type)))

    def test_conditional_rules(self) -> None:
        meta = self.meta("model")
        del meta["base_model"]
        self.assertTrue(any("base_model" in e for e in lint.validate_front_matter(meta, "model")))
        del meta["base_model_relation"]
        self.assertEqual(lint.validate_front_matter(meta, "model"), [])

        meta = self.meta("space")
        del meta["app_port"]
        self.assertTrue(any("app_port" in e for e in lint.validate_front_matter(meta, "space")))
        meta.update(sdk="gradio")
        self.assertTrue(any("sdk_version" in e for e in lint.validate_front_matter(meta, "space")))

        meta = self.meta("dataset")
        meta["license"] = "other"
        errors = lint.validate_front_matter(meta, "dataset")
        self.assertTrue(any("license_name" in e for e in errors))
        self.assertTrue(any("license_link" in e for e in errors))

    def test_value_rules(self) -> None:
        meta = self.meta("kernel")
        meta["library_name"] = "torch"
        self.assertTrue(lint.validate_front_matter(meta, "kernel"))
        meta = self.meta("space")
        meta["short_description"] = "x" * 61
        self.assertTrue(lint.validate_front_matter(meta, "space"))
        meta = self.meta("model")
        meta["szl"]["source_repo"] = "someone-else/repo"
        self.assertTrue(lint.validate_front_matter(meta, "model"))
        meta = self.meta("model")
        meta["base_model_relation"] = "distilled"
        self.assertTrue(lint.validate_front_matter(meta, "model"))

    def test_existing_szl_evidence_keys_are_kept(self) -> None:
        meta = self.meta("model")
        meta["szl"].update(artifact_class="ADAPTER", weights="AVAILABLE", doctrine="v11-LOCKED")
        self.assertEqual(lint.validate_front_matter(meta, "model"), [])

    def test_unknown_schema_keyword_fails_closed(self) -> None:
        schema = json.loads(lint.SCHEMA_PATH.read_text(encoding="utf-8"))
        schema["$defs"]["tags"]["contains"] = {"const": "x"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema.json"
            path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaises(lint.SchemaError):
                lint.load_schema(path)


class ClaimLintTests(unittest.TestCase):
    def test_measured_needs_receipt_in_same_unit(self) -> None:
        self.assertEqual(rules(card("Tests pass. MEASURED.\n")), ["D10"])
        self.assertEqual(rules(card(f"Tests pass. MEASURED ([receipt]({RECEIPT})).\n")), [])
        self.assertEqual(rules(card(f"MEASURED tests pass.\n\n[receipt]({RECEIPT})\n")), ["D10"])

    def test_table_rows_are_separate_units(self) -> None:
        body = (
            "| Thing | Label | Evidence |\n| --- | --- | --- |\n"
            f"| tests | MEASURED | [r]({RECEIPT}) |\n"
            "| bench | MEASURED | none |\n"
        )
        found = findings(card(body))
        self.assertEqual(len(found), 1)
        self.assertIn("bench", found[0].message)

    def test_list_items_are_separate_units(self) -> None:
        body = f"- MEASURED one [r]({RECEIPT})\n- MEASURED two\n  continued line\n"
        found = findings(card(body))
        self.assertEqual(len(found), 1)
        self.assertIn("two", found[0].message)

    def test_benchmark_numbers_need_receipt(self) -> None:
        for text in (
            "Accuracy: 91.2 on the held-out split.",
            "p95 latency 12 ms on a laptop.",
            "Throughput 8,400 tok/s.",
            "It is 2.3x faster than the baseline.",
            "| MMLU | 71.3 |",
            "Reaches 97% on the suite.",
        ):
            with self.subTest(text=text):
                self.assertEqual(rules(card(text + "\n")), ["D10"])
                self.assertEqual(rules(card(f"{text} [receipt]({RECEIPT})\n")), [])

    def test_ordinary_numbers_are_not_benchmarks(self) -> None:
        body = (
            "Released 2026-08-29 as v0.1.0 for torch 2.10.0+cu128.\n\n"
            "The table is 3290x128 and ships `vectors.npz`.\n\n"
            "Uses 16-bit precision and serves 3 users on port 7860.\n"
        )
        self.assertEqual(rules(card(body)), [])

    def test_layout_and_negation_are_not_benchmarks(self) -> None:
        body = (
            '<p align="center"><img src="banner.svg" width="100%"/></p>\n\n'
            "Trust ceiling is advisory, never 100%.\n\n"
            "The table is 3290 x 128.\n"
        )
        self.assertEqual(rules(card(body)), [])
        self.assertEqual(rules(card(f'<p>MEASURED <a href="{RECEIPT}">receipt</a></p>\n')), [])

    def test_label_legend_is_not_a_claim(self) -> None:
        body = "- Doctrine labels in force: MEASURED / REPORTED / UNKNOWN / UNAVAILABLE\n"
        self.assertEqual(rules(card(body)), [])
        self.assertEqual(rules(card("Labels: MEASURED / REPORTED / MODELED / HEURISTIC.\n")), [])
        self.assertEqual(rules(card("Each value is labeled `MEASURED`, `REPORTED`, `SAMPLE`, or `UNAVAILABLE`.\n")), [])
        self.assertEqual(rules(card("Energy is MEASURED or UNAVAILABLE.\n")), ["D10"])
        self.assertEqual(rules(card("MEASURED / REPORTED\n")), ["D10"])

    def test_code_and_comments_are_ignored(self) -> None:
        body = "```text\nMEASURED 99% accuracy: 0.99\n```\n\n<!-- MEASURED 50 ms -->\n\n~~~\nMEASURED\n~~~\n"
        self.assertEqual(rules(card(body)), [])

    def test_reference_style_receipt_links(self) -> None:
        body = f"MEASURED tests pass [receipt][r1].\n\n[r1]: {RECEIPT}\n"
        self.assertEqual(rules(card(body)), [])

    def test_receipt_link_forms(self) -> None:
        good = [
            RECEIPT,
            f"https://github.com/szl-holdings/demo/tree/{SHA}/receipts",
            f"https://raw.githubusercontent.com/szl-holdings/demo/{SHA}/receipts/bench.json",
            f"https://github.com/szl-holdings/Demo/blob/{SHA}/r.json?plain=1#L3",
        ]
        bad = [
            "https://github.com/szl-holdings/demo/blob/main/receipts/bench.json",
            f"https://github.com/szl-holdings/demo/blob/{SHA[:12]}/receipts/bench.json",
            f"https://github.com/someone/demo/blob/{SHA}/receipts/bench.json",
            f"https://huggingface.co/SZLHOLDINGS/demo/blob/{SHA}/BENCH.json",
        ]
        for url in good:
            with self.subTest(url=url):
                self.assertEqual(rules(card(f"MEASURED [r]({url})\n")), [])
        for url in bad:
            with self.subTest(url=url):
                self.assertEqual(rules(card(f"MEASURED [r]({url})\n")), ["D10"])

    def test_receipt_outside_source_repo_is_rejected(self) -> None:
        url = f"https://github.com/szl-holdings/other/blob/{OTHER_SHA}/r.json"
        found = findings(card(f"MEASURED [r]({url})\n"))
        self.assertEqual(len(found), 1)
        self.assertIn("outside the source repo", found[0].message)

    def test_front_matter_measured_and_model_index(self) -> None:
        front = FRONT.replace("tags: [kernel]\n", "tags: [kernel]\nszl-governance:\n  energy: MEASURED-only\n")
        self.assertEqual(rules(card("Body.\n", front)), ["D10"])
        sibling = FRONT.replace(
            "tags: [kernel]\n", f"tags: [kernel]\nszl-governance:\n  energy: MEASURED\n  energy_receipt: {RECEIPT}\n")
        self.assertEqual(rules(card("Body.\n", sibling)), [])
        legend = FRONT.replace(
            "tags: [kernel]\n", "tags: [kernel]\nszl-governance:\n  labels: MEASURED / REPORTED / UNKNOWN\n")
        self.assertEqual(rules(card("Body.\n", legend)), [])
        model_front = (
            "---\nlicense: apache-2.0\nlibrary_name: transformers\ntags: [x]\n"
            "szl: {source_repo: szl-holdings/demo, proof_url: 'https://github.com/szl-holdings/demo'}\n"
            "model-index:\n- name: demo\n  results:\n  - task: {type: text-generation}\n"
            "    metrics: [{type: accuracy, value: 0.9}]\n"
        )
        self.assertEqual(rules(card("Body.\n", model_front + "---\n"), "model"), ["D10"])
        with_source = model_front + f"    source: {{name: receipt, url: '{RECEIPT}'}}\n---\n"
        self.assertEqual(rules(card("Body.\n", with_source), "model"), [])

    def test_parse_errors(self) -> None:
        for text in ("# no front matter\n", "---\nlicense: [\n---\n", "---\n- a list\n---\n", "---\nlicense: x\n"):
            with self.subTest(text=text):
                with self.assertRaises(lint.CardError):
                    lint.lint_text(text, "model")
        with self.assertRaises(lint.CardError):
            lint.lint_text(card("Body.\n"), None)

    def test_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.md"
            bad = Path(tmp) / "bad.md"
            broken = Path(tmp) / "broken.md"
            good.write_text(card(f"MEASURED [r]({RECEIPT})\n"), encoding="utf-8")
            bad.write_text(card("MEASURED\n"), encoding="utf-8")
            broken.write_text("no front matter\n", encoding="utf-8")
            report = Path(tmp) / "report.json"
            sink = io.StringIO()
            with redirect_stdout(sink), redirect_stderr(sink):
                self.assertEqual(lint.main([str(good), "--type", "kernel"]), 0)
                self.assertEqual(lint.main([str(good), str(bad), "--type", "kernel", "--json", str(report)]), 1)
                self.assertEqual(lint.main([str(broken), "--type", "kernel"]), 2)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual([row["ok"] for row in data], [True, False])


if __name__ == "__main__":
    unittest.main(verbosity=2)
