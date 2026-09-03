#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_public_experience_v4.py"

GOOD_HTML = '''<!doctype html><html lang="en"><head>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
html,body{overflow-x:clip} a,button{min-height:44px}
:focus-visible{outline:3px solid currentColor}
input{font-size:16px}
body{padding-left:env(safe-area-inset-left)}
@media(max-width:720px){main{display:block}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style></head><body>
<a class="skip-link" href="#main">Skip</a><main id="main"><h1>Demo</h1>
<a href="#a">A</a><a href="#b">B</a><button>One</button><button>Two</button>
<input aria-label="Search"><select aria-label="Mode"><option>All</option></select>
</main></body></html>'''


class PublicExperienceGateTests(unittest.TestCase):
    def run_gate(self, html: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "index.html"
            path.write_text(textwrap.dedent(html), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CHECKER), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_known_good_mobile_contract_passes(self) -> None:
        result = self.run_gate(GOOD_HTML)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASSED", result.stdout)

    def test_missing_mobile_and_accessibility_contract_fails(self) -> None:
        result = self.run_gate(
            '<!doctype html><html><head></head><body><h2>No main</h2></body></html>'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("viewport", result.stdout)
        self.assertIn("visible keyboard focus", result.stdout)
        self.assertIn("reduced-motion", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
