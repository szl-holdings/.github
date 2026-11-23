// SPDX-License-Identifier: Apache-2.0

const SHA40 = /^[a-f0-9]{40}$/;

export function assertSameBuild(shown: string, evidence: unknown): void {
  if (!SHA40.test(shown)) {
    throw new Error(
      `UI/API build id is missing or not a 40-character revision: ${shown}`,
    );
  }
  const payload = (
    evidence as { receipt?: { payload?: { source_revision?: unknown } } }
  )?.receipt?.payload;
  const evidenceBuild = payload?.source_revision;
  if (typeof evidenceBuild !== 'string' || !SHA40.test(evidenceBuild)) {
    throw new Error(
      'same-build evidence check failed: evidence omitted the build id',
    );
  }
  if (evidenceBuild !== shown) {
    throw new Error(
      `same-build evidence check failed: evidence build ${evidenceBuild} != UI/API build ${shown}`,
    );
  }
}
