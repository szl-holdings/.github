// SPDX-License-Identifier: Apache-2.0
import { spawnSync } from 'node:child_process';
import path from 'node:path';

export default function globalSetup(): void {
  const base = process.env.BASE_URL;
  const api = process.env.API_URL || base;
  if (!base || !api) {
    throw new Error('BASE_URL is required');
  }
  if (process.env.STAGING !== 'true') {
    throw new Error('refusing: STAGING=true is required');
  }
  const script = path.join(process.cwd(), 'canary', 'compare.py');
  const args = [
    script,
    '--check-only',
    '--staging',
    '--canary',
    base,
    '--control',
    api,
  ];
  if (process.env.TARGET_CLASS) {
    args.push('--target-class', process.env.TARGET_CLASS);
  }
  const result = spawnSync('python3', args, { encoding: 'utf-8' });
  if (result.status !== 0) {
    const detail = (result.stdout || result.stderr || 'host refused').trim();
    throw new Error(detail);
  }
}
