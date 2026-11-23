// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8765';
const startFixture = process.env.HARNESS_FIXTURE === '1';
const pixel = devices['Pixel 7'];
const iphone = devices['iPhone 14'];

function portOf(url: string): string {
  const parsed = new URL(url);
  if (parsed.port) return parsed.port;
  return parsed.protocol === 'https:' ? '443' : '80';
}

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  globalSetup: path.join(process.cwd(), 'global-setup.ts'),
  use: {
    baseURL,
    trace: process.env.PW_TRACE === 'on' ? 'on' : 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: startFixture
    ? {
        command: `python3 fixtures/a11oy_fixture.py --port ${portOf(baseURL)}`,
        url: new URL('/api/livez', baseURL).toString(),
        reuseExistingServer: false,
        timeout: 30_000,
        env: {
          ...process.env,
          FIXTURE_GAP: process.env.FIXTURE_GAP || '',
        },
      }
    : undefined,
  projects: [
    { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox-desktop', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit-desktop', use: { ...devices['Desktop Safari'] } },
    { name: 'chromium-pixel7', use: { ...pixel } },
    {
      name: 'firefox-pixel7',
      use: { ...pixel, defaultBrowserType: 'firefox' },
    },
    {
      name: 'webkit-pixel7',
      use: { ...pixel, defaultBrowserType: 'webkit' },
    },
    {
      name: 'chromium-iphone14',
      use: { ...iphone, defaultBrowserType: 'chromium' },
    },
    {
      name: 'firefox-iphone14',
      use: { ...iphone, defaultBrowserType: 'firefox' },
    },
    { name: 'webkit-iphone14', use: { ...iphone } },
  ],
});
