// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assertSameBuild } from './same-build.ts';

const BUILD = '9467fa988ff63c919954adbd8e23e930412321b5';

test('matching receipt build id passes', () => {
  assertSameBuild(BUILD, { receipt: { payload: { source_revision: BUILD } } });
});

test('omitted evidence build id fails', () => {
  assert.throws(
    () => assertSameBuild(BUILD, { receipt: { payload: {} } }),
    /omitted the build id/,
  );
});

test('different evidence build id fails', () => {
  assert.throws(
    () => assertSameBuild(BUILD, {
      receipt: { payload: { source_revision: 'a'.repeat(40) } },
    }),
    /!= UI\/API build/,
  );
});
