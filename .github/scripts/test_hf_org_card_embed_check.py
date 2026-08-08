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
  <main id="szl-hf-main">
    <h1 class="szl-hf-title">Autonomy under authority</h1>
  <nav><a class="szl-hf-nav-item" href="https://example.com">Navigate</a></nav>
    <div class="szl-hf-hero">
      <div class="szl-hf-cta-row szl-hf-actions">
        <a class="szl-hf-button" href="https://szlholdings-readme.static.hf.space/">Open</a>
      </div>
    </div>
  </main>
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
