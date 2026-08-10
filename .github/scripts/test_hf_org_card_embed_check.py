import unittest
from pathlib import Path

import hf_org_card_embed_check as check


def valid_document() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<style>
#szl-hf-org-card {
  --tap: 44px;
}
#szl-hf-org-card .szl-hf-shell {
  width: min(1180px, calc(100% - 40px));
  max-width: 100%;
}
#szl-hf-org-card .szl-hf-button {
  display: inline-flex !important;
  min-height: 48px;
}
#szl-hf-org-card .szl-hf-actions .szl-hf-button {
  width: 100% !important;
}
#szl-hf-org-card nav a {
  min-height: var(--tap);
}
#szl-hf-org-card * {
  overflow-wrap: anywhere;
}
#szl-hf-org-card .szl-hf-hero {
  display: flex;
}
@media (max-width: 640px) {
  #szl-hf-org-card .szl-hf-cta-row,
  #szl-hf-org-card .szl-hf-actions {
    display: flex !important;
  }
  #szl-hf-org-card .szl-hf-actions .szl-hf-button {
    width: 100% !important;
  }
  #szl-hf-org-card .szl-hf-hero {
    min-height: 0;
  }
  #szl-hf-org-card .szl-hf-steps {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  #szl-hf-org-card nav {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (prefers-reduced-motion: reduce) {
  #szl-hf-org-card * { transition: none !important; }
}
@media (prefers-contrast: more) {
  #szl-hf-org-card { color: buttontext; }
}
@media (forced-colors: active) {
  #szl-hf-org-card { forced-color-adjust: none; }
}
#szl-hf-org-card .szl-hf-safe-edges {
  padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
}
</style>
</head>
<body data-szl-surface="company-front-door">
<div id="szl-hf-org-card" data-szl-embed-safe="true">
  <a class="szl-hf-skip" href="#szl-hf-main">Skip to main content</a>
  <img
    class="szl-hf-hero-art"
    src="https://szlholdings-readme.static.hf.space/assets/evidence-lattice-v2.webp"
    alt=""
    width="1800"
    height="776"
    fetchpriority="high"
    decoding="async"
  >
  <main id="szl-hf-main" class="szl-hf-shell">
    <h1 class="szl-hf-title">Autonomy under authority</h1>
  <nav><a class="szl-hf-nav-item" href="https://example.com">Navigate</a></nav>
    <div class="szl-hf-hero">
      <div class="szl-hf-cta-row szl-hf-actions">
        <a class="szl-hf-button" href="https://szlholdings-readme.static.hf.space/">Open</a>
      </div>
    </div>
  </main>
  <ol class="szl-hf-steps"><li class="szl-hf-step">Verify</li></ol>
  <!-- canonical deployment source: https://szlholdings-readme.static.hf.space/deployment.json -->
</div>
</body>
</html>
"""


class EmbedContractTests(unittest.TestCase):
    def test_minimal_embed_safe_document_passes(self):
        self.assertEqual(check.validate_document(valid_document()), [])

    def test_current_org_card_passes(self):
        root = Path(__file__).resolve().parents[2]
        document = (root / "huggingface/org-card/index.html").read_text(
            encoding="utf-8"
        )
        self.assertEqual(check.validate_document(document), [])

    def test_rejects_generic_class_and_unscoped_selector(self):
        document = valid_document().replace("class=\"szl-hf-title\"", "class=\"title\"").replace(
            "#szl-hf-org-card .szl-hf-button {",
            ".button {",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("unscoped class tokens" in item for item in failures)
        )
        self.assertTrue(
            any("unrooted CSS selector" in item for item in failures)
        )

    def test_rejects_unused_generic_css_class(self):
        document = valid_document().replace(
            "</style>", ".legacy-card { color: red; }\n</style>"
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("unscoped CSS classes" in item for item in failures)
        )

    def test_rejects_relative_image_asset(self):
        document = valid_document().replace(
            'src="https://szlholdings-readme.static.hf.space/assets/evidence-lattice-v2.webp"',
            'src="assets/hero.svg"',
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("hero image contract drifted" in item for item in failures)
        )

    def test_rejects_missing_mobile_cta_rule(self):
        document = valid_document().replace(
            "width: 100% !important;", "min-width: 100%;"
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_missing_mobile_evidence_reflow(self):
        document = valid_document().replace(
            "#szl-hf-org-card .szl-hf-steps {\n    grid-template-columns: 1fr;",
            "#szl-hf-org-card .szl-hf-steps {\n    grid-template-columns: repeat(6, 1fr);",
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("single-column mobile evidence loop" in item for item in failures)
        )

    def test_rejects_responsive_rules_outside_intended_media_block(self):
        cases = (
            (
                "  #szl-hf-org-card .szl-hf-actions .szl-hf-button {\n"
                "    width: 100% !important;\n"
                "  }",
                "one-column mobile CTA",
                640,
                "    width: 100% !important;",
                "    width: auto !important;",
            ),
            (
                "  #szl-hf-org-card nav {\n"
                "    display: grid;\n"
                "    grid-template-columns: repeat(2, minmax(0, 1fr));\n"
                "  }",
                "mobile navigation reflow",
                760,
                "    grid-template-columns: repeat(2, minmax(0, 1fr));",
                "    grid-template-columns: none;",
            ),
            (
                "  #szl-hf-org-card .szl-hf-hero {\n"
                "    min-height: 0;\n"
                "  }",
                "compact mobile hero",
                640,
                "    min-height: 0;",
                "    min-height: 500px;",
            ),
            (
                "  #szl-hf-org-card .szl-hf-steps {\n"
                "    grid-template-columns: 1fr;\n"
                "  }",
                "single-column mobile evidence loop",
                640,
                "    grid-template-columns: 1fr;",
                "    grid-template-columns: repeat(6, 1fr);",
            ),
        )
        for rule, label, max_width, required, override in cases:
            with self.subTest(label=label):
                document = valid_document().replace(rule, "", 1)
                document = document.replace("</style>", f"{rule}\n</style>", 1)
                failures = check.validate_document(document)
                self.assertTrue(any(label in item for item in failures))

                commented = valid_document().replace(rule, "", 1)
                commented = commented.replace(
                    "</style>",
                    f"/* @media (max-width: {max_width}px) {{\n{rule}\n}} */\n"
                    "</style>",
                    1,
                )
                failures = check.validate_document(commented)
                self.assertTrue(any(label in item for item in failures))

                commented_in_place = valid_document().replace(
                    rule, f"/* {rule} */", 1
                )
                failures = check.validate_document(commented_in_place)
                self.assertTrue(any(label in item for item in failures))

                contradictory = valid_document().replace(rule, "", 1)
                contradictory = contradictory.replace(
                    f"@media (max-width: {max_width}px) {{",
                    f"@media (max-width: {max_width}px) {{\n"
                    f"  @media (min-width: {max_width + 1}px) {{\n"
                    f"{rule}\n"
                    "  }",
                    1,
                )
                failures = check.validate_document(contradictory)
                self.assertTrue(any(label in item for item in failures))

                nested_under_selector = valid_document().replace(rule, "", 1)
                nested_under_selector = nested_under_selector.replace(
                    f"@media (max-width: {max_width}px) {{",
                    f"@media (max-width: {max_width}px) {{\n"
                    "  #szl-hf-org-card .szl-hf-never-match {\n"
                    f"{rule}\n"
                    "  }",
                    1,
                )
                failures = check.validate_document(nested_under_selector)
                self.assertTrue(any(label in item for item in failures))

                overridden_in_rule = valid_document().replace(
                    required, f"{required}\n{override}", 1
                )
                failures = check.validate_document(overridden_in_rule)
                self.assertTrue(any(label in item for item in failures))

                later_override = valid_document().replace(
                    "</style>",
                    f"@media (max-width: {max_width}px) {{\n"
                    f"{rule.replace(required, override)}\n"
                    "}\n</style>",
                    1,
                )
                failures = check.validate_document(later_override)
                self.assertTrue(any(label in item for item in failures))

    def test_rejects_commented_bounded_shell(self):
        shell_rule = (
            "#szl-hf-org-card .szl-hf-shell {\n"
            "  width: min(1180px, calc(100% - 40px));\n"
            "  max-width: 100%;\n"
            "}"
        )
        document = valid_document()
        self.assertIn(shell_rule, document)
        failures = check.validate_document(
            document.replace(shell_rule, f"/* {shell_rule} */", 1)
        )
        self.assertTrue(
            any("bounded embedded shell" in item for item in failures)
        )

    def test_rejects_conditionally_bounded_shell(self):
        shell_rule = (
            "#szl-hf-org-card .szl-hf-shell {\n"
            "  width: min(1180px, calc(100% - 40px));\n"
            "  max-width: 100%;\n"
            "}"
        )
        document = valid_document()
        self.assertIn(shell_rule, document)
        document = document.replace(shell_rule, "", 1)
        document = document.replace(
            "</style>",
            f"@media (min-width: 9999px) {{\n{shell_rule}\n}}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("bounded embedded shell" in item for item in failures)
        )

    def test_rejects_nested_bounded_shell(self):
        shell_rule = (
            "#szl-hf-org-card .szl-hf-shell {\n"
            "  width: min(1180px, calc(100% - 40px));\n"
            "  max-width: 100%;\n"
            "}"
        )
        document = valid_document()
        self.assertIn(shell_rule, document)
        document = document.replace(shell_rule, "", 1)
        document = document.replace(
            "</style>",
            "#szl-hf-org-card .szl-hf-never-match {\n"
            f"{shell_rule}\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("bounded embedded shell" in item for item in failures)
        )

    def test_rejects_later_bounded_shell_override(self):
        document = valid_document().replace(
            "</style>",
            "#szl-hf-org-card .szl-hf-shell { max-width: 1180px; }\n"
            "</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("bounded embedded shell" in item for item in failures)
        )

    def test_rejects_more_specific_mobile_cta_override(self):
        document = valid_document().replace(
            "</style>",
            "@media (max-width: 640px) {\n"
            "  #szl-hf-org-card main .szl-hf-actions .szl-hf-button {\n"
            "    width: auto !important;\n"
            "  }\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_alternate_selector_mobile_cta_override(self):
        document = valid_document().replace(
            "</style>",
            "@media (max-width: 640px) {\n"
            "  #szl-hf-org-card .szl-hf-button.szl-hf-primary {\n"
            "    width: auto !important;\n"
            "  }\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_supported_mobile_cta_override(self):
        document = valid_document().replace(
            "</style>",
            "@supports (display: grid) {\n"
            "  #szl-hf-org-card .szl-hf-actions .szl-hf-button {\n"
            "    width: auto !important;\n"
            "  }\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_navigation_grid_shorthand_override(self):
        document = valid_document().replace(
            "</style>",
            "@media (max-width: 760px) {\n"
            "  #szl-hf-org-card nav { grid: none; }\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("mobile navigation reflow" in item for item in failures)
        )

    def test_rejects_narrower_mobile_cta_override(self):
        document = valid_document().replace(
            "</style>",
            "@media (max-width: 390px) {\n"
            "  #szl-hf-org-card .szl-hf-actions .szl-hf-button {\n"
            "    width: auto !important;\n"
            "  }\n"
            "}\n</style>",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_unbounded_embedded_shell(self):
        document = valid_document().replace(
            "max-width: 100%;", "max-width: 1180px;", 1
        )
        failures = check.validate_document(document)
        self.assertTrue(any("bounded embedded shell" in item for item in failures))

    def test_rejects_relative_navigation(self):
        document = valid_document().replace(
            'href="https://example.com"', 'href="/docs"'
        )
        failures = check.validate_document(document)
        self.assertTrue(any("navigation targets" in item for item in failures))

    def test_rejects_missing_aria_label_target(self):
        document = valid_document().replace(
            '<main id="szl-hf-main" class="szl-hf-shell">',
            '<main id="szl-hf-main" class="szl-hf-shell" '
            'aria-labelledby="szl-hf-missing-title">',
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("aria-labelledby targets are missing" in item for item in failures)
        )

    def test_rejects_missing_embed_marker(self):
        document = valid_document().replace(
            ' data-szl-embed-safe="true"', ""
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("data-szl-embed-safe=true" in item for item in failures)
        )


if __name__ == "__main__":
    unittest.main()
