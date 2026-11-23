// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

const WCAG_22_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

async function tabTo(page: Page, locator: ReturnType<Page['locator']>): Promise<void> {
  for (let i = 0; i < 40; i += 1) {
    if (await locator.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  throw new Error('keyboard did not reach the next control');
}

test('key controls expose names and roles', async ({ page }) => {
  await page.goto('/command-centre');
  await expect(page.getByRole('link', { name: 'Skip to work' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Command centre' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Refresh status' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'What are we working on?' })).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Atelier operator credential' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send governed request' })).toBeVisible();
  await expect(page.getByRole('status')).toHaveText(/No request has been sent/);
});

test('page meets WCAG 2.2 AA tags', async ({ page }) => {
  await page.goto('/command-centre');
  const results = await new AxeBuilder({ page }).withTags(WCAG_22_AA).analyze();
  expect(results.violations).toEqual([]);
});

test('keyboard-only journey reaches a real answer', async ({ page }) => {
  const credential = process.env.A11OY_OPERATOR_CREDENTIAL;
  if (!credential) throw new Error('A11OY_OPERATOR_CREDENTIAL is required');
  await page.goto('/command-centre');
  const send = page.getByRole('button', { name: 'Send governed request' });
  await expect(send).toBeEnabled();
  await tabTo(page, page.getByRole('link', { name: 'Skip to work' }));
  await page.keyboard.press('Enter');
  await tabTo(page, page.getByRole('textbox', { name: 'Atelier operator credential' }));
  await page.keyboard.type(credential);
  await tabTo(page, page.getByRole('textbox', { name: 'What are we working on?' }));
  await page.keyboard.type('What is the public status of this build?');
  await tabTo(page, send);
  await page.keyboard.press('Enter');
  await expect(page.locator('#answer')).toBeVisible();
  const results = await new AxeBuilder({ page }).withTags(WCAG_22_AA).analyze();
  expect(results.violations).toEqual([]);
});
