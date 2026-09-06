#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Behavioral regressions for repeated source-native responsive planning.

All GitHub calls are replaced by an in-memory file tree. No provider writes,
repository execution, or visual-performance claims are made by these tests.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.github' / 'scripts'


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Files:
    def __init__(self, files: dict[str, str]):
        self.files = dict(files)

    def tree(self, _repo: str, _ref: str):
        return [{'path': p} for p in sorted(self.files)]

    def file(self, _repo: str, path: str, _ref: str):
        return self.files[path], 'fixture-blob'

    def apply(self, changes):
        for change in changes:
            self.files[change.path] = change.content


class ResponsiveHostIdempotenceTests(unittest.TestCase):
    def setUp(self):
        self.core = load('responsive_idempotence_core', 'rollout_holographic_spaces_v2.py')
        self.responsive = load('responsive_idempotence_adapter', 'responsive_space_contract.py')
        self.css = '/* SZL Public Experience v3 fixture */\n:root { --fixture: 1; }\n'
        self.js = '/* __SZL_PUBLIC_EXPERIENCE_V3__ fixture */\n'
        # Only the payload bytes are injected; both planning functions are real.
        with patch.object(self.responsive, '_read_assets', return_value=(self.css, self.js)):
            self.responsive.install(self.core)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.map_path = Path(self.directory.name) / 'sources.json'
        self.core.LOCAL_SOURCE_MAP = self.map_path
        self.repo = {'full_name': 'szl-holdings/immune', 'default_branch': 'main'}
        self.space = self.core.Space('immune', 'docker', 'RUNNING', 'https://huggingface.co/spaces/SZLHOLDINGS/immune')
        self.map_root('frontend/index.html')
        self.html = '<!doctype html><html><head><title>Product</title></head><body><main>Keep this product</main></body></html>'

    def map_root(self, root):
        self.map_path.write_text(json.dumps({'schema': 'szl.public-space-source-map/v1', 'sources': [{'space': 'immune', 'repo': self.repo['full_name'], 'source_root': root, 'ownership': 'source-owned-capability-channel'}]}), encoding='utf-8')

    def plan(self, files):
        return self.core.plan_repository(files, self.repo, [self.space], 1000, 'reviewed fixture', 'combined css', 'combined javascript')

    def test_second_pass_does_not_create_another_shell(self):
        files = Files({'frontend/index.html': self.html, 'frontend/szl-holo-v2.css': 'product css', 'frontend/szl-holo-v2.js': 'product js'})
        first = self.plan(files)
        self.assertEqual(first.adapter, 'responsive-existing-host')
        self.assertEqual({c.path for c in first.changes}, {'frontend/szl-holo-v2.css', 'frontend/szl-holo-v2.js'})
        files.apply(first.changes)
        for _ in range(3):
            again = self.plan(files)
            self.assertEqual(again.status, 'already-integrated')
            self.assertEqual(again.adapter, 'responsive-existing-host')
            self.assertEqual(again.changes, [])
        self.assertEqual(files.files['frontend/index.html'], self.html)
        self.assertFalse(any('szl-space-hologram' in path for path in files.files))

    def test_already_current_product_host_is_a_no_op_on_first_observation(self):
        files = Files({'frontend/index.html': self.html, 'frontend/szl-holo-v2.css': 'product css\n' + self.css, 'frontend/szl-holo-v2.js': 'product js\n' + self.js})
        result = self.plan(files)
        self.assertEqual(result.status, 'already-integrated')
        self.assertEqual(result.changes, [])
        self.assertEqual(result.adapter, 'responsive-existing-host')

    def test_one_stale_member_updates_only_that_member_and_then_settles(self):
        files = Files({'frontend/index.html': self.html, 'frontend/szl-holo-v2.css': 'product css\n' + self.css, 'frontend/szl-holo-v2.js': 'product js'})
        first = self.plan(files)
        self.assertEqual([c.path for c in first.changes], ['frontend/szl-holo-v2.js'])
        files.apply(first.changes)
        self.assertEqual(self.plan(files).changes, [])

    def test_new_static_root_still_receives_assets_once(self):
        files = Files({'frontend/index.html': self.html})
        first = self.plan(files)
        self.assertEqual(first.adapter, 'responsive-explicit-static')
        self.assertEqual(len(first.changes), 3)
        files.apply(first.changes)
        again = self.plan(files)
        self.assertEqual(again.status, 'already-integrated')
        self.assertEqual(again.changes, [])

    def test_generated_asset_updates_do_not_modify_existing_html(self):
        marked = self.core.adapt_static(self.html, './szl-space-hologram.css', './szl-space-hologram.js', 'immune')
        files = Files({'frontend/index.html': marked, 'frontend/szl-space-hologram.css': 'old css', 'frontend/szl-space-hologram.js': 'old javascript'})
        first = self.plan(files)
        self.assertEqual({c.path for c in first.changes}, {'frontend/szl-space-hologram.css', 'frontend/szl-space-hologram.js'})
        files.apply(first.changes)
        self.assertEqual(self.plan(files).changes, [])
        self.assertEqual(files.files['frontend/index.html'], marked)

    def test_incomplete_host_pair_is_not_claimed_as_integrated(self):
        files = Files({'frontend/index.html': self.html, 'frontend/szl-holo-v2.css': self.css})
        result = self.plan(files)
        self.assertEqual(result.status, 'planned')
        self.assertEqual(result.adapter, 'responsive-explicit-static')
        self.assertIn('frontend/index.html', {c.path for c in result.changes})


if __name__ == '__main__':
    unittest.main(verbosity=2)
