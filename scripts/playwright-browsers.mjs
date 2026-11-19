// SPDX-License-Identifier: Apache-2.0
const wanted = (process.env.BROWSERS || 'chromium,firefox,webkit')
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean);
const known = ['chromium', 'firefox', 'webkit'];
const selected = known.filter((browser) => wanted.includes(browser));
if (selected.length === 0) {
  console.error(`no Playwright browsers for: ${wanted.join(',')}`);
  process.exit(1);
}
process.stdout.write(selected.join(' '));
