// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assertRealAnswer } from './result-honesty.ts';

test('a completed sentence is a real result', () => {
  assertRealAnswer(
    'The public status of this build is an observed command-centre turn.',
  );
});

test('placeholder text is rejected', () => {
  assert.throws(
    () => assertRealAnswer('This is a placeholder result for the demo page.'),
    /placeholder/,
  );
});

test('a snapshot stand-in is rejected', () => {
  assert.throws(
    () => assertRealAnswer('Snapshot of an earlier command-centre answer.'),
    /snapshot or stale/,
  );
});
