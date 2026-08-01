import unittest
from pathlib import Path

import hf_org_card_embed_check as check


def valid_document() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<style>
#szl-hf-org-card .szl-hf-button {
  display: inline-flex !important;
}
@media (max-width: 640px) {
  #szl-hf-org-card .szl-hf-cta-row {
    display: grid !important;
    grid-template-columns: 1fr;
  }
  #szl-hf-org-card .szl-hf-button {
    width: 100% !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  #szl-hf-org-card * { transition: none !important; }
}
</style>
</head>
<body data-szl-surface="company-front-door">
<div id="szl-hf-org-card" data-szl-embed-safe="true">
  <a class="szl-hf-skip" href="#szl-hf-main">Skip to main content</a>
  <main id="szl-hf-main">
    <h1 class="szl-hf-title">Autonomy under authority</h1>
    <div class="szl-hf-hero">
      <div class="szl-hf-cta-row">
        <a class="szl-hf-button" href="https://example.com">Open</a>
      </div>
    </div>
  </main>
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
        document = valid_document().replace(
            'class="szl-hf-hero"', 'class="hero"'
        ).replace(
            "#szl-hf-org-card .szl-hf-button {",
            ".button {",
            1,
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("unscoped class tokens" in item for item in failures)
        )
        self.assertTrue(
            any("unscoped CSS selector" in item for item in failures)
        )

    def test_rejects_relative_image_asset(self):
        document = valid_document().replace(
            '<div class="szl-hf-hero">',
            '<div class="szl-hf-hero"><img src="assets/hero.svg" alt="">',
        )
        failures = check.validate_document(document)
        self.assertTrue(
            any("relative or unsafe runtime assets" in item for item in failures)
        )
        self.assertTrue(
            any("must not depend on image assets" in item for item in failures)
        )

    def test_rejects_missing_mobile_cta_rule(self):
        document = valid_document().replace(
            "grid-template-columns: 1fr;", "justify-content: stretch;"
        )
        failures = check.validate_document(document)
        self.assertTrue(any("mobile CTA contract" in item for item in failures))

    def test_rejects_relative_navigation(self):
        document = valid_document().replace(
            'href="https://example.com"', 'href="/docs"'
        )
        failures = check.validate_document(document)
        self.assertTrue(any("navigation targets" in item for item in failures))

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
