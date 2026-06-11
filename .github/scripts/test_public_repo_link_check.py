#!/usr/bin/env python3
"""Self-test for the in-page (deep) anchor checking in public_repo_link_check.py.

Task #412 taught the public-repo link checker to catch *broken in-page section
links* in docs — the ``#fragment`` anchors that the absolute-blob check could
never see because they have no http(s) host:

  * same-page  -> ``[x](#heading)`` whose anchor must exist in the CURRENT page.
  * relative   -> ``[x](./OTHER.md#heading)`` whose anchor must exist in THAT
                  Markdown file (resolved within the same repo).

The Pass-3 resolution loop in ``main()`` is thin glue over four pure, fully
deterministic helpers; this test pins their contracts (and the composition that
actually decides "broken vs present") with NO network, stdlib ``unittest`` only,
so CI needs only a github-owned ``actions/setup-python`` to run it. Run by FILE
PATH (``python3 .github/scripts/test_public_repo_link_check.py``) — the leading
``.github`` dir is not an importable package.

What is pinned:
  1. ``extract_local_anchor_links`` extracts same-page + relative-.md anchors and
     SKIPS the things that are not in-repo heading anchors (http(s)/mailto,
     site-root ``/path``, no-fragment links, non-Markdown relative targets), and
     de-dups by (kind, target, fragment).
  2. ``_resolve_relative_path`` resolves ``./`` and ``../`` within the repo and
     returns None for anything escaping the root (so we never raise a false
     positive on a path we cannot resolve).
  3. ``heading_anchors`` slugifies GitHub-style (dup-suffixing, code-fence
     skipping, explicit ``{#id}``, raw ``<a name>`` / ``user-content-`` HTML).
  4. ``_normalize_fragment`` / ``_is_line_anchor`` (``#L12`` / ``#L1-L4`` carry
     no heading and must be ignored).
  5. End-to-end (offline) composition: a broken same-page / broken relative
     fragment is flagged, a valid one is NOT — the exact decision the Pass-3
     loop makes.
"""
from __future__ import annotations

import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "public_repo_link_check.py")

_spec = importlib.util.spec_from_file_location("public_repo_link_check", _MODULE_PATH)
assert _spec and _spec.loader
prl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prl)


class ExtractLocalAnchorLinks(unittest.TestCase):
    def _kinds(self, text):
        return {(k, t, f) for (k, t, f, _u) in prl.extract_local_anchor_links(text)}

    def test_same_page_and_relative_md(self):
        md = (
            "See [setup](#setup) and the [guide](./docs/GUIDE.md#install).\n"
            "Also [up](../README.md#usage).\n"
        )
        got = self._kinds(md)
        self.assertIn(("same-page", "", "setup"), got)
        self.assertIn(("relative", "./docs/GUIDE.md", "install"), got)
        self.assertIn(("relative", "../README.md", "usage"), got)

    def test_skips_non_inrepo_and_no_fragment(self):
        md = (
            "[ext](https://example.com/x#frag)\n"          # absolute -> skip
            "[mail](mailto:a@b.com)\n"                      # mailto -> skip
            "[proto](//host/p#f)\n"                          # protocol-relative -> skip
            "[root](/org/repo#readme)\n"                     # site-root -> skip
            "[nofrag](./docs/GUIDE.md)\n"                    # no #fragment -> skip
            "[png](./img/diagram.png#x)\n"                   # non-markdown -> skip
        )
        self.assertEqual(self._kinds(md), set())

    def test_dedup_by_kind_target_fragment(self):
        md = "[a](#top)\n[b](#top)\n[c](./X.md#h)\n[d](./X.md#h)\n"
        got = prl.extract_local_anchor_links(md)
        keys = [(k, t, f) for (k, t, f, _u) in got]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), {("same-page", "", "top"), ("relative", "./X.md", "h")})


class ResolveRelativePath(unittest.TestCase):
    def test_same_dir(self):
        self.assertEqual(prl._resolve_relative_path("README.md", "./DOC.md"), "DOC.md")

    def test_subdir_from_root(self):
        self.assertEqual(
            prl._resolve_relative_path("README.md", "docs/GUIDE.md"), "docs/GUIDE.md")

    def test_parent_within_repo(self):
        self.assertEqual(
            prl._resolve_relative_path("docs/sub/PAGE.md", "../GUIDE.md"), "docs/GUIDE.md")

    def test_escape_returns_none(self):
        self.assertIsNone(prl._resolve_relative_path("README.md", "../../etc/passwd"))
        self.assertIsNone(prl._resolve_relative_path("docs/G.md", "../../../x.md"))

    def test_absolute_returns_none(self):
        self.assertIsNone(prl._resolve_relative_path("README.md", "/abs/path.md"))


class HeadingAnchors(unittest.TestCase):
    def test_basic_and_duplicate_suffix(self):
        md = "# Hello World\n## Hello World\n### Notes\n"
        anc = prl.heading_anchors(md)
        self.assertIn("hello-world", anc)
        self.assertIn("hello-world-1", anc)  # 2nd identical heading
        self.assertIn("notes", anc)

    def test_code_fence_headings_ignored(self):
        md = "# Real\n```\n# Fake In Fence\n```\n"
        anc = prl.heading_anchors(md)
        self.assertIn("real", anc)
        self.assertNotIn("fake-in-fence", anc)

    def test_explicit_id_and_html_anchor(self):
        md = "## Custom Heading {#custom-id}\n<a name=\"user-content-legacy\"></a>\n"
        anc = prl.heading_anchors(md)
        self.assertIn("custom-id", anc)
        self.assertIn("legacy", anc)  # user-content- prefix stripped


class FragmentHelpers(unittest.TestCase):
    def test_normalize_strips_user_content_and_lowercases(self):
        self.assertEqual(prl._normalize_fragment("User-Content-Foo"), "foo")
        self.assertEqual(prl._normalize_fragment("Setup%20Steps"), "setup steps")

    def test_line_anchors_detected(self):
        self.assertTrue(prl._is_line_anchor("l12"))
        self.assertTrue(prl._is_line_anchor("l1-l4"))
        self.assertFalse(prl._is_line_anchor("installation"))


class EndToEndComposition(unittest.TestCase):
    """The exact decision Pass-3 makes, exercised offline."""

    def _broken(self, page_text, target_text=None):
        """Return the set of (kind, fragment) the checker would FLAG as broken."""
        flagged = set()
        for kind, target, frag, _url in prl.extract_local_anchor_links(page_text):
            nf = prl._normalize_fragment(frag)
            if not nf or prl._is_line_anchor(nf):
                continue
            anchors = (prl.heading_anchors(page_text) if kind == "same-page"
                       else prl.heading_anchors(target_text or ""))
            if nf not in anchors:
                flagged.add((kind, frag))
        return flagged

    def test_same_page_broken_vs_valid(self):
        page = "# Setup\nGo to [ok](#setup) and [bad](#nope).\n"
        flagged = self._broken(page)
        self.assertIn(("same-page", "nope"), flagged)
        self.assertNotIn(("same-page", "setup"), flagged)

    def test_relative_broken_vs_valid(self):
        page = "[ok](./G.md#install) and [bad](./G.md#missing)\n"
        target = "# Install\nText.\n"
        flagged = self._broken(page, target_text=target)
        self.assertIn(("relative", "missing"), flagged)
        self.assertNotIn(("relative", "install"), flagged)

    def test_line_anchor_never_flagged(self):
        page = "See [src](./G.md#L12).\n"
        # Even with an empty target file, an #L12 line anchor must be ignored.
        self.assertEqual(self._broken(page, target_text=""), set())


class BareUrlBraceStripping(unittest.TestCase):
    """Regression (Task #412 false-positive batch): a github.com/szl-holdings URL
    wrapped in a LaTeX/BibTeX ``\\url{...}`` field or a ``{{ template }}`` must NOT
    capture the trailing ``}`` brace(s) as part of the URL. The a11oy cookbook
    recipes carry ``howpublished = {\\url{https://github.com/szl-holdings/...md}},``
    citations; the unfixed bare-URL scan grabbed ``...md}}`` and reported a bogus
    HTTP 404 on a link whose real (brace-free) target returns 200."""

    _CLEAN = ("https://github.com/szl-holdings/szl-cookbook/blob/main/"
              "recipes/11-kitaev-surface-drift-detection.md")

    def test_bibtex_url_field_org(self):
        text = "  howpublished = {\\url{" + self._CLEAN + "}},\n"
        urls = prl._clickthrough_urls(text)
        self.assertIn(self._CLEAN, urls)
        self.assertFalse(any("}" in u for u in urls), urls)
        self.assertEqual(prl._repo_from_url(self._CLEAN), "szl-cookbook")

    def test_double_brace_template_org(self):
        text = "Cite {{" + self._CLEAN + "}} for the surface code.\n"
        urls = prl._clickthrough_urls(text)
        self.assertIn(self._CLEAN, urls)
        self.assertFalse(any("}" in u for u in urls), urls)

    def test_external_bare_url_brace(self):
        ext = "https://example.com/path/to/doc"
        text = "\\url{" + ext + "}}"
        urls = prl._clickthrough_urls(text, include_bare_external=True)
        self.assertIn(ext, urls)
        self.assertFalse(any("}" in u for u in urls), urls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
