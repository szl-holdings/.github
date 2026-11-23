// SPDX-License-Identifier: Apache-2.0
const wanted = (process.env.BROWSERS || 'chromium,firefox,webkit')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);

const projects = [
  'chromium-desktop',
  'chromium-pixel7',
  'chromium-iphone14',
  'firefox-desktop',
  'firefox-pixel7',
  'firefox-iphone14',
  'webkit-desktop',
  'webkit-pixel7',
  'webkit-iphone14',
];

const selected = projects.filter((name) => wanted.some((browser) => name.startsWith(`${browser}-`)));
if (selected.length === 0) {
  console.error(`no Playwright projects for browsers: ${wanted.join(',')}`);
  process.exit(1);
}
process.stdout.write(selected.map((name) => `--project=${name}`).join(' '));
