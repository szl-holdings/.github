import unittest
from pathlib import Path
from types import SimpleNamespace

import public_front_door_check as check


class FrontMatterTests(unittest.TestCase):
    def test_reads_emoji_from_leading_front_matter(self):
        document = "---\nsdk: static\nemoji: 🛡️\n---\n# Card\n"
        self.assertEqual(check.front_matter_value(document, "emoji"), "🛡️")

    def test_unquotes_front_matter_scalar(self):
        document = '---\nshort_description: "Bounded action"\n---\n'
        self.assertEqual(
            check.front_matter_value(document, "short_description"),
            "Bounded action",
        )

    def test_ignores_value_in_card_body(self):
        document = "---\nsdk: static\n---\n# Card\nemoji: 🛡️\n"
        self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_rejects_non_leading_front_matter(self):
        document = "# Card\n---\nemoji: 🛡️\n---\n"
        self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_rejects_duplicate_emoji_metadata(self):
        document = (
            f"---\nemoji: {check.HUB_CARD_EMOJI}\nemoji: {check.HUB_CARD_EMOJI}\n---\n"
        )
        self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_thumbnail_requires_exact_canonical_url(self):
        exact = f"---\nthumbnail: {check.HUB_CARD_THUMBNAIL}\n---\n"
        collision = f"---\nthumbnail: {check.HUB_CARD_THUMBNAIL}.evil\n---\n"
        duplicate = (
            f"---\nthumbnail: {check.HUB_CARD_THUMBNAIL}\n"
            f"thumbnail: {check.HUB_CARD_THUMBNAIL}.evil\n---\n"
        )
        self.assertTrue(check.has_canonical_thumbnail(exact))
        self.assertFalse(check.has_canonical_thumbnail(collision))
        self.assertFalse(check.has_canonical_thumbnail(duplicate))

    def test_rejects_multiline_alias_and_unsupported_top_level_metadata(self):
        cases = (
            "---\nemoji: |\n  shield\n---\n",
            "---\nemoji: *approved\n---\n",
            "---\n!!str emoji: shield\n---\n",
            "---\nemoji:\n  nested: shield\n---\n",
        )
        for document in cases:
            with self.subTest(document=document):
                self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_rejects_invalid_quoted_plain_and_unrelated_metadata(self):
        cases = (
            "---\nemoji: 'a'b'\n---\n",
            "---\nemoji: a: b\n---\n",
            f"---\nsdk: static\nsdk: static\nemoji: {check.HUB_CARD_EMOJI}\n---\n",
            f"---\nother: *alias\nemoji: {check.HUB_CARD_EMOJI}\n---\n",
            f"---\n!!str other: value\nemoji: {check.HUB_CARD_EMOJI}\n---\n",
        )
        for document in cases:
            with self.subTest(document=document):
                self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_rejects_invalid_or_implicitly_typed_emoji_scalars(self):
        for value in ("]", "@x", "123", "2026-08-01"):
            document = f"---\nemoji: {value}\n---\n"
            with self.subTest(value=value):
                self.assertIsNone(check.front_matter_value(document, "emoji"))

    def test_short_description_accepts_exact_hub_limit(self):
        document = (
            "---\nshort_description: "
            + ("x" * check.HUB_CARD_SHORT_DESCRIPTION_MAX_CHARS)
            + "\n---\n"
        )
        self.assertEqual(check.hub_short_description_length(document), 60)
        self.assertTrue(check.short_description_within_limit(document))

    def test_short_description_rejects_over_hub_limit(self):
        document = (
            "---\nshort_description: "
            + ("x" * (check.HUB_CARD_SHORT_DESCRIPTION_MAX_CHARS + 1))
            + "\n---\n"
        )
        self.assertEqual(check.hub_short_description_length(document), 61)
        self.assertFalse(check.short_description_within_limit(document))

    def test_measures_quoted_and_folded_short_description(self):
        quoted = '---\nshort_description: "Clear boundaries"\n---\n'
        folded = (
            "---\nshort_description: >-\n  "
            + ("x" * 29)
            + "\n  "
            + ("y" * 30)
            + "\n---\n"
        )
        self.assertEqual(check.hub_short_description_length(quoted), 16)
        self.assertEqual(check.hub_short_description_length(folded), 60)
        self.assertTrue(check.short_description_within_limit(folded))

    def test_counts_leading_blank_line_in_folded_scalar(self):
        document = "---\nshort_description: >-\n\n  " + ("x" * 60) + "\n---\n"
        self.assertEqual(check.hub_short_description_length(document), 61)
        self.assertFalse(check.short_description_within_limit(document))

    def test_counts_spaces_retained_on_overindented_blank_block_line(self):
        document = "---\nshort_description: >-\n  " + ("x" * 58) + "\n    \n---\n"
        self.assertEqual(check.hub_short_description_length(document), 61)
        self.assertFalse(check.short_description_within_limit(document))

    def test_rejects_empty_block_short_description(self):
        for document in (
            "---\nshort_description: >-\n---\n",
            "---\nshort_description: |-\n\n---\n",
        ):
            with self.subTest(document=document):
                self.assertIsNone(check.hub_short_description_length(document))
                self.assertFalse(check.short_description_within_limit(document))

    def test_rejects_duplicate_alias_null_and_multiline_flow_values(self):
        cases = (
            "---\nshort_description: ok\nshort_description: duplicate\n---\n",
            "---\nshort_description: *description\n---\n",
            "---\nshort_description: null\n---\n",
            "---\nshort_description: quoted\n  continuation\n---\n",
            (
                "---\n!!str short_description: hidden\n"
                "short_description: " + ("x" * 61) + "\n---\n"
            ),
            "---\n!!str other_key: value\nshort_description: ok\n---\n",
        )
        for document in cases:
            with self.subTest(document=document):
                self.assertIsNone(check.hub_short_description_length(document))
                self.assertFalse(check.short_description_within_limit(document))

    def test_rejects_invalid_yaml_implicit_non_strings_and_empty_strings(self):
        values = (
            "a: b",
            "]",
            "@x",
            "123",
            "1.5",
            "2026-08-01",
            "yes",
            "ON",
            '""',
            "''",
        )
        for value in values:
            document = f"---\nshort_description: {value}\n---\n"
            with self.subTest(value=value):
                self.assertIsNone(check.hub_short_description_length(document))
                self.assertFalse(check.short_description_within_limit(document))

    def test_accepts_explicit_string_that_looks_implicitly_typed(self):
        document = '---\nshort_description: "2026-08-01"\n---\n'
        self.assertEqual(check.hub_short_description_length(document), 10)
        self.assertTrue(check.short_description_within_limit(document))

    def test_org_card_short_description_fits_hugging_face_limit(self):
        root = Path(__file__).resolve().parents[2]
        document = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
        self.assertTrue(check.short_description_within_limit(document))


class MarkdownLayoutTests(unittest.TestCase):
    def test_detects_table_separator(self):
        self.assertTrue(check.has_markdown_table("| A | B |\n| --- | --- |\n"))

    def test_accepts_stacked_cards(self):
        self.assertFalse(check.has_markdown_table("### 01 / Command\n\nOpen a11oy.\n"))


class WorkflowPushValueTests(unittest.TestCase):
    def test_reads_active_push_path(self):
        workflow = 'on:\n  push:\n    paths:\n      - "profile/assets/**"\n'
        self.assertEqual(
            check.workflow_push_values(workflow, "paths"),
            {"profile/assets/**"},
        )

    def test_reads_quoted_on_and_inline_main_branch(self):
        workflow = '"on":\n  push:\n    branches: [main]\n'
        branches = check.workflow_push_values(workflow, "branches")
        self.assertEqual(branches, {"main"})
        self.assertTrue(check.push_branches_are_exact(branches))

    def test_negative_main_branch_exclusion_fails_closed(self):
        workflow = 'on:\n  push:\n    branches: [main, "!main"]\n'
        branches = check.workflow_push_values(workflow, "branches")
        self.assertEqual(branches, {"main", "!main"})
        self.assertFalse(check.push_branches_are_exact(branches))

    def test_reads_single_quoted_path_with_comment(self):
        workflow = (
            "on:\n  push:\n    paths:\n"
            "      - 'huggingface/org-card/**' # publication inputs\n"
        )
        self.assertEqual(
            check.workflow_push_values(workflow, "paths"),
            {"huggingface/org-card/**"},
        )

    def test_ignores_commented_path(self):
        workflow = 'on:\n  push:\n    paths:\n      # - "profile/assets/**"\n'
        self.assertEqual(check.workflow_push_values(workflow, "paths"), set())

    def test_ignores_same_value_outside_push_paths(self):
        workflow = (
            'env:\n  WATCH: "profile/assets/**"\non:\n  push:\n    branches: [main]\n'
        )
        self.assertEqual(check.workflow_push_values(workflow, "paths"), set())

    def test_ignores_fake_push_paths_inside_block_scalar(self):
        workflow = (
            "jobs:\n  audit:\n    steps:\n      - run: |\n"
            "          on:\n            push:\n              paths:\n"
            '                - "profile/assets/**"\n'
        )
        self.assertEqual(check.workflow_push_values(workflow, "paths"), set())

    def test_ignores_tagged_and_anchored_block_scalar_contents(self):
        for header in ("!!str |", "&copy |", "!!str &copy >-2"):
            workflow = (
                f"name: {header}\n"
                "  on:\n    push:\n      paths:\n"
                '        - "profile/assets/**"\n'
            )
            with self.subTest(header=header):
                self.assertEqual(check.workflow_push_values(workflow, "paths"), set())

    def test_multiline_quoted_scalar_cannot_spoof_root_trigger(self):
        for prefix in ("", "!!str ", "&copy ", "!!str &copy ", "&copy !!str "):
            for quote in ('"', "'"):
                workflow = (
                    f"name: {prefix}{quote}fake\n"
                    "on:\n  push:\n    paths:\n      - profile/assets/**\n"
                    f"end{quote}\n'on': pull_request\n"
                )
                with self.subTest(prefix=prefix, quote=quote):
                    self.assertEqual(
                        check.workflow_push_values(workflow, "paths"),
                        {check.UNSUPPORTED_PUSH_VALUE},
                    )

    def test_multiline_flow_collection_cannot_spoof_root_trigger(self):
        required = ", ".join(sorted(check.REQUIRED_PUSH_PATHS))
        workflow = (
            "jobs: { build: { runs-on: ubuntu-latest, strategy: { matrix: { on:\n"
            "[\npush:\n[\nbranches: [main]\n,\n"
            f"paths: [{required}]\n]\n]\n"
            "} }, steps: [{run: echo ok}] } }\n"
            "'on': pull_request\n"
        )
        self.assertEqual(
            check.workflow_push_values(workflow, "paths"),
            {check.UNSUPPORTED_PUSH_VALUE},
        )
        self.assertEqual(
            check.workflow_push_values(workflow, "branches"),
            {check.UNSUPPORTED_PUSH_VALUE},
        )

    def test_negative_push_path_fails_source_coverage_closed(self):
        workflow = (
            "on:\n  push:\n    paths:\n"
            '      - "profile/assets/**"\n'
            '      - "!profile/assets/**"\n'
        )
        paths = check.workflow_push_values(workflow, "paths")
        self.assertEqual(paths, {"profile/assets/**", "!profile/assets/**"})
        self.assertFalse(
            check.source_is_watched(
                "profile/assets/evidence-lattice-v2.webp",
                paths,
            )
        )

    def test_negative_anchor_and_alias_fail_source_coverage_closed(self):
        variants = (
            '&neg "!profile/assets/**"',
            '&neg !!str "!profile/assets/**"',
            "*neg",
        )
        for variant in variants:
            workflow = (
                'negative: &neg "!profile/assets/**"\n'
                "on:\n  push:\n    paths:\n"
                '      - "profile/assets/**"\n'
                f"      - {variant}\n"
            )
            paths = check.workflow_push_values(workflow, "paths")
            with self.subTest(variant=variant):
                self.assertIn(check.UNSUPPORTED_PUSH_VALUE, paths)
                self.assertFalse(
                    check.source_is_watched(
                        "profile/assets/evidence-lattice-v2.webp",
                        paths,
                    )
                )

    def test_manifest_source_is_covered_by_recursive_path(self):
        self.assertTrue(
            check.source_is_watched(
                "profile/assets/evidence-lattice-v2.webp",
                {"profile/assets/**"},
            )
        )
        self.assertFalse(
            check.source_is_watched(
                "profile/README.md",
                {"profile/assets/**"},
            )
        )

    def test_recursive_path_rejects_sibling_prefix_collision(self):
        self.assertFalse(
            check.source_is_watched(
                "profile/assets-old/hero.webp",
                {"profile/assets/**"},
            )
        )


class PublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("C:/repo")

    def files_for_expected_bindings(self):
        return [
            SimpleNamespace(destination=destination, source=self.root / source)
            for destination, source in check.REQUIRED_PUBLICATION_BINDINGS.items()
        ]

    def expected_contract(self):
        return {
            "target": dict(check.EXPECTED_PUBLICATION_TARGET),
            "source_repository": check.EXPECTED_SOURCE_REPOSITORY,
            "smoke": dict(check.EXPECTED_SMOKE),
        }

    def test_requires_exact_publication_destination_and_smoke_contract(self):
        self.assertEqual(
            check.publication_contract_issues(self.expected_contract()), {}
        )

    def test_rejects_redirected_publication_contract_fields(self):
        variants = (
            ("target", "repo_id", "SZLHOLDINGS/other"),
            ("target", "live_base_url", "https://other.static.hf.space"),
            ("source_repository", None, "szl-holdings/other"),
            ("smoke", "path", "/forged"),
            ("smoke", "required_marker", "forged-marker"),
        )
        for section, key, value in variants:
            contract = self.expected_contract()
            if key is None:
                contract[section] = value
            else:
                contract[section][key] = value
            with self.subTest(section=section, key=key):
                self.assertIn(section, check.publication_contract_issues(contract))

    def test_requires_exact_twelve_source_destination_pairs(self):
        self.assertEqual(len(check.REQUIRED_PUBLICATION_BINDINGS), 12)
        issues = check.publication_binding_issues(
            self.root,
            self.files_for_expected_bindings(),
        )
        self.assertFalse(any(issues.values()))

    def test_rejects_existing_destination_bound_to_wrong_source(self):
        files = self.files_for_expected_bindings()
        files[0] = SimpleNamespace(
            destination=files[0].destination,
            source=self.root / "profile/assets/wrong.svg",
        )
        issues = check.publication_binding_issues(self.root, files)
        self.assertEqual(len(issues["mismatched"]), 1)

    def test_rejects_missing_binding(self):
        files = self.files_for_expected_bindings()[1:]
        issues = check.publication_binding_issues(self.root, files)
        self.assertEqual(len(issues["mismatched"]), 1)

    def test_rejects_unexpected_destination(self):
        files = self.files_for_expected_bindings()
        files.append(
            SimpleNamespace(
                destination="assets/unexpected.svg",
                source=self.root / "profile/assets/unexpected.svg",
            )
        )
        issues = check.publication_binding_issues(self.root, files)
        self.assertEqual(issues["unexpected"], ["assets/unexpected.svg"])

    def test_rejects_duplicate_destination(self):
        files = self.files_for_expected_bindings()
        files.append(files[0])
        issues = check.publication_binding_issues(self.root, files)
        self.assertEqual(issues["duplicates"], [files[0].destination])


class WebPTests(unittest.TestCase):
    def test_reads_canonical_dimensions(self):
        root = Path(__file__).resolve().parents[2]
        data = (root / check.CANONICAL_WEBP).read_bytes()
        self.assertEqual(check.webp_dimensions(data), check.WEBP_DIMENSIONS)
        self.assertTrue(check.canonical_webp_is_pinned(data))
        self.assertLessEqual(len(data), check.MAX_WEBP_BYTES)

    def test_rejects_mutated_canonical_webp_digest(self):
        root = Path(__file__).resolve().parents[2]
        data = bytearray((root / check.CANONICAL_WEBP).read_bytes())
        data[-1] ^= 1
        self.assertFalse(check.canonical_webp_is_pinned(bytes(data)))

    def test_rejects_non_webp_bytes(self):
        self.assertIsNone(check.webp_dimensions(b"not-a-webp"))

    def test_rejects_header_only_vp8x_container(self):
        vp8x_payload = b"\x00\x00\x00\x00" + b"\x0f\x00\x00" + b"\x0f\x00\x00"
        data = (
            b"RIFF"
            + (22).to_bytes(4, "little")
            + b"WEBP"
            + b"VP8X"
            + (10).to_bytes(4, "little")
            + vp8x_payload
        )
        self.assertEqual(len(data), 30)
        self.assertIsNone(check.webp_dimensions(data))

    def test_rejects_header_only_vp8_and_minimal_vp8l_containers(self):
        root = Path(__file__).resolve().parents[2]
        canonical = (root / check.CANONICAL_WEBP).read_bytes()
        vp8_header = canonical[20:30]
        vp8 = (
            b"RIFF"
            + (22).to_bytes(4, "little")
            + b"WEBP"
            + b"VP8 "
            + (10).to_bytes(4, "little")
            + vp8_header
        )
        vp8l_payload = b"\x2f\x00\x00\x00\x00"
        vp8l = (
            b"RIFF"
            + (18).to_bytes(4, "little")
            + b"WEBP"
            + b"VP8L"
            + (5).to_bytes(4, "little")
            + vp8l_payload
            + b"\x00"
        )
        self.assertIsNone(check.webp_dimensions(vp8))
        self.assertIsNone(check.webp_dimensions(vp8l))

    def test_rejects_nonzero_odd_chunk_padding(self):
        root = Path(__file__).resolve().parents[2]
        canonical = (root / check.CANONICAL_WEBP).read_bytes()
        forged = bytearray(canonical)
        forged.extend(b"JUNK\x01\x00\x00\x00x\xff")
        forged[4:8] = (len(forged) - 8).to_bytes(4, "little")
        self.assertIsNone(check.webp_dimensions(bytes(forged)))


class SurfaceParserTests(unittest.TestCase):
    def test_counts_full_card_links(self):
        parser = check.SurfaceParser()
        parser.feed(
            '<body data-szl-surface="company-front-door"><main><h1>Title</h1>'
            '<a class="path" href="/one">One</a>'
            '<a class="card featured" href="/two">Two</a>'
            "</main></body>"
        )
        self.assertEqual(parser.path_link_count, 1)
        self.assertEqual(parser.card_link_count, 1)


class CheckCountingTests(unittest.TestCase):
    def test_require_counts_passes_and_failures(self):
        failures = check.FailureList()
        check.require(True, "pass", failures)
        check.require(False, "fail", failures)
        self.assertEqual(failures.checks, 2)
        self.assertEqual(failures, ["fail"])


if __name__ == "__main__":
    unittest.main()
