// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';
import { assertRealAnswer } from '../src/result-honesty.ts';
import { assertSameBuild } from '../src/same-build.ts';

test.describe('a11oy critical journey', () => {
  test.beforeEach(({ }, testInfo) => {
    test.skip(
      testInfo.project.use.isMobile !== true,
      'the critical journey opens on a mobile viewport',
    );
  });

  test('mobile turn returns a real result and same-build evidence', async ({ page }) => {
    const credential = process.env.A11OY_OPERATOR_CREDENTIAL;
    if (!credential) {
      throw new Error('A11OY_OPERATOR_CREDENTIAL is required');
    }
    const apiUrl = process.env.API_URL || process.env.BASE_URL;
    if (!apiUrl) {
      throw new Error('API_URL or BASE_URL is required');
    }

    await page.goto('/command-centre');
    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();
    expect(viewport!.width).toBeLessThan(500);

    const snapshot = page.getByText(/snapshot/i);
    if (await snapshot.count()) {
      await expect(snapshot.first()).toBeVisible();
    }
    const stale = page.getByText(/\bstale\b/i);
    if (await stale.count()) {
      await expect(stale.first()).toBeVisible();
    }

    const source = page.locator('#source-sha');
    await expect(source).toHaveText(/^[a-f0-9]{40}$/);
    const uiBuild = (await source.innerText()).trim();
    const buildResponse = await page.request.get(`${apiUrl}/api/build-info`);
    expect(buildResponse.ok()).toBeTruthy();
    const buildBody = await buildResponse.json();
    const apiBuild = String(buildBody.build?.revision || '');
    expect(apiBuild).toBe(uiBuild);

    await page.locator('#operator-key').fill(credential);
    await page.locator('#prompt').fill('What is the public status of this build?');
    await page.locator('#send').click();

    const answer = page.locator('#answer');
    await expect(answer).toBeVisible();
    const answerText = (await answer.innerText()).trim();
    assertRealAnswer(answerText);
    if (await snapshot.count()) {
      expect(answerText.toLowerCase()).not.toContain('snapshot');
    }
    if (await stale.count()) {
      expect(answerText.toLowerCase()).not.toContain('stale');
    }

    await page.locator('#receipt-panel summary').click();
    const evidence = JSON.parse(await page.locator('#receipt').innerText());
    expect(evidence.state).toBe('COMPLETED');
    expect(evidence.retry_safe).toBe(false);
    assertSameBuild(uiBuild, evidence);
  });
});
